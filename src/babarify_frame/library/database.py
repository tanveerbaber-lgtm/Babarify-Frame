"""SQLite store for library folders, media, history and playlists (M6), and bookmarks (M8).

Design rules:
* Local only: one file in the user's app-data folder; nothing is uploaded.
* Versioned schema (``PRAGMA user_version``). Each migration runs in one transaction, so a
  crash mid-migration leaves the previous version intact.
* Recovery: a file that is not a database or fails ``PRAGMA quick_check`` is moved aside
  (``library.corrupt-<time>.db``) and a fresh database is created; ``recovered`` explains
  what happened so the UI can say so once. A database written by a *newer* version is never
  modified: the app runs with an empty in-memory library and ``read_only_reason`` set.
* Thread safety: one connection guarded by a lock. The scanner writes in batches, so the UI
  thread waits at most one short transaction.
* Files on disk are never deleted or modified here; "remove" means remove the record.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from babarify_frame.library.history import is_finished
from babarify_frame.library.models import (
    Bookmark,
    HistoryEntry,
    LibraryFolder,
    MediaEntry,
    Playlist,
    PlaylistItem,
    SortOrder,
    path_key,
)

log = logging.getLogger(__name__)

# Migration N brings the schema from version N-1 to N. Never edit a released migration: add one.
MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (  # 1: folders, media, history
        """CREATE TABLE folders(
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL,
            path_key TEXT NOT NULL UNIQUE,
            added_at REAL NOT NULL,
            available INTEGER NOT NULL DEFAULT 1)""",
        """CREATE TABLE media(
            id INTEGER PRIMARY KEY,
            folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            path_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            added_at REAL NOT NULL,
            scanned_at REAL NOT NULL,
            available INTEGER NOT NULL DEFAULT 1,
            probed INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER,
            width INTEGER,
            height INTEGER,
            video_codec TEXT,
            audio_codec TEXT,
            thumbnail TEXT)""",
        "CREATE INDEX media_folder ON media(folder_id)",
        "CREATE INDEX media_name ON media(name COLLATE NOCASE)",
        """CREATE TABLE history(
            path_key TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            title TEXT NOT NULL,
            position_ms INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER,
            finished INTEGER NOT NULL DEFAULT 0,
            play_count INTEGER NOT NULL DEFAULT 0,
            last_played_at REAL NOT NULL)""",
        "CREATE INDEX history_recent ON history(last_played_at DESC)",
    ),
    (  # 2: duplicate detection and playlists
        "ALTER TABLE media ADD COLUMN content_key TEXT",
        "CREATE INDEX media_content ON media(content_key)",
        """CREATE TABLE playlists(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at REAL NOT NULL)""",
        """CREATE TABLE playlist_items(
            id INTEGER PRIMARY KEY,
            playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            path TEXT NOT NULL,
            title TEXT NOT NULL)""",
        "CREATE INDEX playlist_items_order ON playlist_items(playlist_id, position)",
    ),
    (  # 3: timeline bookmarks (M8)
        """CREATE TABLE bookmarks(
            id INTEGER PRIMARY KEY,
            path_key TEXT NOT NULL,
            path TEXT NOT NULL,
            position_ms INTEGER NOT NULL,
            label TEXT NOT NULL,
            created_at REAL NOT NULL)""",
        "CREATE INDEX bookmarks_media ON bookmarks(path_key, position_ms)",
    ),
)
SCHEMA_VERSION = len(MIGRATIONS)
MAX_PLAYLIST_NAME = 120
MAX_BOOKMARK_LABEL = 120
MAX_BOOKMARKS_PER_FILE = 200


class LibraryError(Exception):
    """A user-facing refusal (e.g. adding a folder that is already in the library)."""


@dataclass(frozen=True)
class ScanRecord:
    path: str
    folder_id: int
    size: int
    mtime: float
    content_key: str | None


@dataclass(frozen=True)
class ProbeRecord:
    duration_ms: int | None
    width: int | None
    height: int | None
    video_codec: str | None
    audio_codec: str | None
    thumbnail: str | None


def default_database_path() -> Path:
    base = os.environ.get("BABARIFY_CONFIG_DIR") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Babarify" / "Frame" / "library.db"


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class LibraryDatabase:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path  # None = in memory (tests)
        self.recovered: str | None = None
        self.read_only_reason: str | None = None
        self._lock = threading.RLock()
        self._conn = self._open()

    # ------------------------------------------------------------- opening
    def _connect(self, target: str) -> sqlite3.Connection:
        conn = sqlite3.connect(target, check_same_thread=False, isolation_level=None, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _open(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = None
        if self.path is None:
            conn = self._connect(":memory:")
            self._migrate(conn)
            return conn
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = self._connect(str(self.path))
            check = conn.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                conn.close()
                raise sqlite3.DatabaseError(f"quick_check: {check}")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                conn.close()
                self.read_only_reason = (
                    f"The library was created by a newer version of Babarify Frame (schema {version}). "
                    "It was left untouched; this session uses an empty library."
                )
                log.warning("library schema %s is newer than %s; not opened", version, SCHEMA_VERSION)
                conn = self._connect(":memory:")
                self._migrate(conn)
                return conn
            conn.execute("PRAGMA journal_mode = WAL")
            self._migrate(conn)
            return conn
        except sqlite3.DatabaseError as exc:
            log.warning("library database unusable (%s); starting fresh", exc)
            if conn is not None:
                conn.close()  # Windows: an open handle would block moving the file aside
            moved = self._quarantine()
            if moved is None:
                # The damaged file could not be moved (e.g. locked): never overwrite it.
                self.read_only_reason = (
                    "The library database is damaged and could not be set aside; "
                    "this session uses an empty library."
                )
                conn = self._connect(":memory:")
                self._migrate(conn)
                return conn
            self.recovered = (
                "The library database was damaged and has been replaced with an empty one. "
                f"The damaged file was kept as {moved.name}."
            )
            conn = self._connect(str(self.path))
            conn.execute("PRAGMA journal_mode = WAL")
            self._migrate(conn)
            return conn

    def _quarantine(self) -> Path | None:
        assert self.path is not None
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.path.with_name(f"{self.path.stem}.corrupt-{stamp}{self.path.suffix}")
        try:
            os.replace(self.path, target)
        except OSError as exc:
            log.warning("could not move damaged library %s: %s", self.path, exc)
            return None
        for suffix in ("-wal", "-shm"):
            side = Path(str(self.path) + suffix)
            if side.exists():
                with suppress(OSError):
                    os.replace(side, Path(str(target) + suffix))
        return target

    @staticmethod
    def _migrate(conn: sqlite3.Connection, target: int = SCHEMA_VERSION) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number in range(version + 1, target + 1):
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in MIGRATIONS[number - 1]:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {number}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            log.info("library schema migrated to %s", number)

    @property
    def schema_version(self) -> int:
        with self._lock:
            return int(self._conn.execute("PRAGMA user_version").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def _query(self, sql: str, params: Sequence[object] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------- folders
    def add_folder(self, path: str) -> LibraryFolder:
        folder = Path(path)
        if not folder.is_dir():
            raise LibraryError(f"{path} is not a folder")
        key = path_key(str(folder))
        for existing in self.folders():
            other = path_key(existing.path)
            if key == other:
                raise LibraryError(f"{existing.path} is already in the library")
            if key.startswith(other.rstrip(os.sep) + os.sep):
                raise LibraryError(f"{path} is inside {existing.path}, which is already in the library")
        now = time.time()
        with self._transaction() as conn:
            cur = conn.execute(
                "INSERT INTO folders(path, path_key, added_at) VALUES (?, ?, ?)",
                (os.path.abspath(path), key, now),
            )
            new_id = int(cur.lastrowid or 0)
            # A parent of existing folders replaces them; their media move over unchanged.
            prefix = _escape_like(key.rstrip(os.sep) + os.sep) + "%"
            children = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM folders WHERE id != ? AND path_key LIKE ? ESCAPE '\\'", (new_id, prefix)
                )
            ]
            for child in children:
                conn.execute("UPDATE media SET folder_id = ? WHERE folder_id = ?", (new_id, child))
                conn.execute("DELETE FROM folders WHERE id = ?", (child,))
        return LibraryFolder(new_id, os.path.abspath(path), now)

    def remove_folder(self, folder_id: int) -> None:
        """Remove a folder and its library entries. Files and playback history are kept."""
        with self._transaction() as conn:
            conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))

    def folders(self) -> list[LibraryFolder]:
        return [
            LibraryFolder(r["id"], r["path"], r["added_at"], bool(r["available"]))
            for r in self._query("SELECT * FROM folders ORDER BY path COLLATE NOCASE")
        ]

    def set_folder_available(self, folder_id: int, available: bool) -> None:
        with self._transaction() as conn:
            conn.execute("UPDATE folders SET available = ? WHERE id = ?", (int(available), folder_id))
            if not available:
                conn.execute("UPDATE media SET available = 0 WHERE folder_id = ?", (folder_id,))

    # --------------------------------------------------------------- media
    def known_files(self, folder_id: int) -> dict[str, tuple[int, float, str | None]]:
        """path_key -> (size, mtime, content_key) for a folder: lets the scanner skip unchanged files."""
        rows = self._query(
            "SELECT path_key, size, mtime, content_key FROM media WHERE folder_id = ?", (folder_id,)
        )
        return {r["path_key"]: (r["size"], r["mtime"], r["content_key"]) for r in rows}

    def upsert_media(self, records: Iterable[ScanRecord], scanned_at: float) -> int:
        """Insert new files, refresh changed ones (they are probed again). Returns rows written."""
        count = 0
        with self._transaction() as conn:
            for rec in records:
                key = path_key(rec.path)
                row = conn.execute("SELECT id, size, mtime FROM media WHERE path_key = ?", (key,)).fetchone()
                if row is None:
                    conn.execute(
                        """INSERT INTO media(folder_id, path, path_key, name, size, mtime, added_at,
                           scanned_at, content_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (rec.folder_id, rec.path, key, os.path.basename(rec.path), rec.size, rec.mtime,
                         scanned_at, scanned_at, rec.content_key),
                    )  # fmt: skip
                elif (row["size"], row["mtime"]) != (rec.size, rec.mtime):
                    conn.execute(
                        """UPDATE media SET folder_id = ?, path = ?, size = ?, mtime = ?, scanned_at = ?,
                           available = 1, probed = 0, thumbnail = NULL, content_key = ? WHERE id = ?""",
                        (
                            rec.folder_id,
                            rec.path,
                            rec.size,
                            rec.mtime,
                            scanned_at,
                            rec.content_key,
                            row["id"],
                        ),
                    )
                else:
                    conn.execute(
                        "UPDATE media SET folder_id = ?, scanned_at = ?, available = 1 WHERE id = ?",
                        (rec.folder_id, scanned_at, row["id"]),
                    )
                count += 1
        return count

    def mark_missing(self, folder_id: int, scanned_at: float) -> int:
        """Files of a folder not seen by a completed scan become unavailable (kept, shown greyed)."""
        with self._transaction() as conn:
            cur = conn.execute(
                "UPDATE media SET available = 0 WHERE folder_id = ? AND scanned_at < ? AND available = 1",
                (folder_id, scanned_at),
            )
            return cur.rowcount

    def media_to_probe(self, limit: int = 50) -> list[tuple[int, str]]:
        rows = self._query(
            "SELECT id, path FROM media WHERE probed = 0 AND available = 1 ORDER BY added_at DESC LIMIT ?",
            (limit,),
        )
        return [(r["id"], r["path"]) for r in rows]

    def set_probe_result(self, media_id: int, result: ProbeRecord | None) -> None:
        """Store metadata; ``None`` means the file could not be read (it stays, without details)."""
        with self._transaction() as conn:
            if result is None:
                conn.execute("UPDATE media SET probed = 1 WHERE id = ?", (media_id,))
                return
            conn.execute(
                """UPDATE media SET probed = 1, duration_ms = ?, width = ?, height = ?, video_codec = ?,
                   audio_codec = ?, thumbnail = ? WHERE id = ?""",
                (result.duration_ms, result.width, result.height, result.video_codec, result.audio_codec,
                 result.thumbnail, media_id),
            )  # fmt: skip

    def media(
        self, search: str = "", sort: SortOrder = SortOrder.NAME, limit: int = 10_000, offset: int = 0
    ) -> list[MediaEntry]:
        order = {
            SortOrder.NAME: "m.name COLLATE NOCASE, m.path COLLATE NOCASE",
            SortOrder.DATE_ADDED: "m.added_at DESC, m.name COLLATE NOCASE",
            SortOrder.RECENTLY_PLAYED: (
                "h.last_played_at IS NULL, h.last_played_at DESC, m.name COLLATE NOCASE"
            ),
            SortOrder.DURATION: "m.duration_ms IS NULL, m.duration_ms DESC, m.name COLLATE NOCASE",
            SortOrder.SIZE: "m.size DESC, m.name COLLATE NOCASE",
        }[sort]
        where, params = "", []
        terms = search.split()
        if terms:
            clauses = []
            for term in terms:
                clauses.append("m.path LIKE ? ESCAPE '\\'")
                params.append(f"%{_escape_like(term)}%")
            where = "WHERE " + " AND ".join(clauses)
        rows = self._query(
            f"""SELECT m.*, h.position_ms AS h_position, h.last_played_at AS h_played,
                (SELECT COUNT(*) FROM media d WHERE d.content_key = m.content_key AND d.id != m.id) AS dups
                FROM media m LEFT JOIN history h ON h.path_key = m.path_key
                {where} ORDER BY {order} LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        )
        return [self._media_entry(r) for r in rows]

    @staticmethod
    def _media_entry(r: sqlite3.Row) -> MediaEntry:
        return MediaEntry(
            id=r["id"],
            path=r["path"],
            name=r["name"],
            folder_id=r["folder_id"],
            size=r["size"],
            mtime=r["mtime"],
            added_at=r["added_at"],
            available=bool(r["available"]),
            duration_ms=r["duration_ms"],
            width=r["width"],
            height=r["height"],
            video_codec=r["video_codec"],
            audio_codec=r["audio_codec"],
            thumbnail=r["thumbnail"],
            probed=bool(r["probed"]),
            content_key=r["content_key"],
            duplicates=int(r["dups"] or 0) if r["content_key"] else 0,
            position_ms=int(r["h_position"] or 0),
            last_played_at=r["h_played"],
        )

    def media_by_path(self, path: str) -> MediaEntry | None:
        rows = self._query(
            """SELECT m.*, h.position_ms AS h_position, h.last_played_at AS h_played,
               (SELECT COUNT(*) FROM media d WHERE d.content_key = m.content_key AND d.id != m.id) AS dups
               FROM media m LEFT JOIN history h ON h.path_key = m.path_key WHERE m.path_key = ?""",
            (path_key(path),),
        )
        return self._media_entry(rows[0]) if rows else None

    def duplicates_of(self, media_id: int) -> list[str]:
        rows = self._query(
            """SELECT d.path FROM media m JOIN media d ON d.content_key = m.content_key AND d.id != m.id
               WHERE m.id = ? AND m.content_key IS NOT NULL ORDER BY d.path""",
            (media_id,),
        )
        return [r["path"] for r in rows]

    def counts(self) -> tuple[int, int, int]:
        """(all media, unavailable media, media waiting for metadata)."""
        row = self._query(
            """SELECT COUNT(*) AS total, COALESCE(SUM(available = 0), 0) AS missing,
               COALESCE(SUM(probed = 0 AND available = 1), 0) AS pending FROM media"""
        )[0]
        return int(row["total"]), int(row["missing"]), int(row["pending"])

    def remove_media(self, media_ids: Iterable[int]) -> None:
        with self._transaction() as conn:
            conn.executemany("DELETE FROM media WHERE id = ?", [(i,) for i in media_ids])

    def remove_unavailable(self) -> int:
        with self._transaction() as conn:
            return conn.execute("DELETE FROM media WHERE available = 0").rowcount

    def thumbnails_in_use(self) -> set[str]:
        return {
            r["thumbnail"] for r in self._query("SELECT thumbnail FROM media WHERE thumbnail IS NOT NULL")
        }

    # ------------------------------------------------------------- history
    def record_play(self, path: str, title: str, duration_ms: int | None) -> HistoryEntry:
        now = time.time()
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO history(path_key, path, title, duration_ms, play_count, last_played_at)
                   VALUES (?, ?, ?, ?, 1, ?)
                   ON CONFLICT(path_key) DO UPDATE SET path = excluded.path, title = excluded.title,
                   duration_ms = COALESCE(excluded.duration_ms, duration_ms), play_count = play_count + 1,
                   last_played_at = excluded.last_played_at""",
                (path_key(path), path, title, duration_ms, now),
            )
        entry = self.history_for(path)
        assert entry is not None
        return entry

    def save_position(self, path: str, title: str, position_ms: int, duration_ms: int | None) -> None:
        position_ms = max(0, int(position_ms))
        finished = is_finished(position_ms, duration_ms)
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO history(path_key, path, title, position_ms, duration_ms, finished,
                   last_played_at) VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(path_key) DO UPDATE SET position_ms = excluded.position_ms,
                   duration_ms = COALESCE(excluded.duration_ms, duration_ms), finished = excluded.finished,
                   last_played_at = excluded.last_played_at""",
                (path_key(path), path, title, position_ms, duration_ms, int(finished), time.time()),
            )

    def mark_finished(self, path: str) -> None:
        with self._transaction() as conn:
            conn.execute(
                """UPDATE history SET finished = 1, position_ms = COALESCE(duration_ms, position_ms)
                   WHERE path_key = ?""",
                (path_key(path),),
            )

    def _history_rows(self, where: str, params: Sequence[object], limit: int) -> list[HistoryEntry]:
        rows = self._query(
            f"""SELECT h.*, m.thumbnail AS thumb, m.available AS m_available FROM history h
                LEFT JOIN media m ON m.path_key = h.path_key {where}
                ORDER BY h.last_played_at DESC LIMIT ?""",
            (*params, limit),
        )
        out = []
        for r in rows:
            available = bool(r["m_available"]) if r["m_available"] is not None else _local_exists(r["path"])
            out.append(
                HistoryEntry(
                    path=r["path"],
                    title=r["title"],
                    position_ms=r["position_ms"],
                    duration_ms=r["duration_ms"],
                    finished=bool(r["finished"]),
                    play_count=r["play_count"],
                    last_played_at=r["last_played_at"],
                    available=available,
                    thumbnail=r["thumb"],
                )
            )
        return out

    def history_for(self, path: str) -> HistoryEntry | None:
        rows = self._history_rows("WHERE h.path_key = ?", (path_key(path),), 1)
        return rows[0] if rows else None

    def recent(self, limit: int = 20) -> list[HistoryEntry]:
        return self._history_rows("", (), limit)

    def continue_watching(self, limit: int = 12, min_position_ms: int = 10_000) -> list[HistoryEntry]:
        rows = self._history_rows(
            "WHERE h.finished = 0 AND h.position_ms >= ?", (min_position_ms,), limit * 2
        )
        return [e for e in rows if e.available][:limit]

    def remove_history(self, path: str) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM history WHERE path_key = ?", (path_key(path),))

    def clear_history(self) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM history")

    def history_count(self) -> int:
        return int(self._query("SELECT COUNT(*) FROM history")[0][0])

    # ----------------------------------------------------------- playlists
    @staticmethod
    def _clean_name(name: str) -> str:
        clean = " ".join(name.split())[:MAX_PLAYLIST_NAME]
        if not clean:
            raise LibraryError("A playlist needs a name")
        return clean

    def create_playlist(self, name: str) -> Playlist:
        clean, now = self._clean_name(name), time.time()
        with self._transaction() as conn:
            cur = conn.execute("INSERT INTO playlists(name, created_at) VALUES (?, ?)", (clean, now))
        return Playlist(int(cur.lastrowid or 0), clean, now)

    def rename_playlist(self, playlist_id: int, name: str) -> None:
        with self._transaction() as conn:
            conn.execute("UPDATE playlists SET name = ? WHERE id = ?", (self._clean_name(name), playlist_id))

    def delete_playlist(self, playlist_id: int) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def playlists(self) -> list[Playlist]:
        rows = self._query(
            """SELECT p.*, (SELECT COUNT(*) FROM playlist_items i WHERE i.playlist_id = p.id) AS n
               FROM playlists p ORDER BY p.name COLLATE NOCASE"""
        )
        return [Playlist(r["id"], r["name"], r["created_at"], r["n"]) for r in rows]

    def playlist_items(self, playlist_id: int) -> list[PlaylistItem]:
        rows = self._query(
            "SELECT * FROM playlist_items WHERE playlist_id = ? ORDER BY position", (playlist_id,)
        )
        return [
            PlaylistItem(
                r["id"], r["playlist_id"], r["position"], r["path"], r["title"], _local_exists(r["path"])
            )
            for r in rows
        ]

    def add_to_playlist(self, playlist_id: int, paths: Iterable[str]) -> None:
        with self._transaction() as conn:
            end = conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM playlist_items WHERE playlist_id = ?", (playlist_id,)
            ).fetchone()[0]
            for offset, path in enumerate(paths, 1):
                conn.execute(
                    "INSERT INTO playlist_items(playlist_id, position, path, title) VALUES (?, ?, ?, ?)",
                    (playlist_id, end + offset, path, os.path.basename(path)),
                )

    def remove_playlist_item(self, item_id: int) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM playlist_items WHERE id = ?", (item_id,))

    def move_playlist_item(self, item_id: int, delta: int) -> None:
        """Move an item up (delta < 0) or down; positions stay contiguous."""
        with self._transaction() as conn:
            row = conn.execute("SELECT playlist_id FROM playlist_items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                return
            ids = [
                r[0]
                for r in conn.execute(
                    "SELECT id FROM playlist_items WHERE playlist_id = ? ORDER BY position", (row[0],)
                )
            ]
            index = ids.index(item_id)
            target = max(0, min(len(ids) - 1, index + delta))
            ids.insert(target, ids.pop(index))
            for position, iid in enumerate(ids):
                conn.execute("UPDATE playlist_items SET position = ? WHERE id = ?", (position, iid))

    # ----------------------------------------------------------- bookmarks
    @staticmethod
    def _clean_label(label: str) -> str:
        return " ".join(label.split())[:MAX_BOOKMARK_LABEL].strip()

    def add_bookmark(self, path: str, position_ms: int, label: str) -> Bookmark:
        """Add a bookmark; an empty label is allowed (the UI shows the time instead)."""
        position_ms, clean, now = max(0, int(position_ms)), self._clean_label(label), time.time()
        key = path_key(path)
        with self._transaction() as conn:
            count = conn.execute("SELECT COUNT(*) FROM bookmarks WHERE path_key = ?", (key,)).fetchone()[0]
            if count >= MAX_BOOKMARKS_PER_FILE:
                raise LibraryError(f"A file can have at most {MAX_BOOKMARKS_PER_FILE} bookmarks")
            cur = conn.execute(
                """INSERT INTO bookmarks(path_key, path, position_ms, label, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (key, path, position_ms, clean, now),
            )
        return Bookmark(int(cur.lastrowid or 0), path, position_ms, clean, now)

    def bookmarks_for(self, path: str) -> list[Bookmark]:
        rows = self._query(
            "SELECT * FROM bookmarks WHERE path_key = ? ORDER BY position_ms, id", (path_key(path),)
        )
        return [Bookmark(r["id"], r["path"], r["position_ms"], r["label"], r["created_at"]) for r in rows]

    def rename_bookmark(self, bookmark_id: int, label: str) -> None:
        with self._transaction() as conn:
            conn.execute(
                "UPDATE bookmarks SET label = ? WHERE id = ?", (self._clean_label(label), bookmark_id)
            )

    def delete_bookmark(self, bookmark_id: int) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))

    def clear_bookmarks(self, path: str) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM bookmarks WHERE path_key = ?", (path_key(path),))


def _local_exists(path: str) -> bool:
    return "://" in path or os.path.exists(path)
