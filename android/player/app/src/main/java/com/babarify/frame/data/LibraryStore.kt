package com.babarify.frame.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.babarify.frame.core.SortOrder

data class LibraryFolder(val id: Long, val uri: String, val name: String)

data class MediaEntry(
    val id: Long,
    val uri: String,
    val name: String,
    val folderId: Long,
    val size: Long,
    val addedAt: Long,
    val durationMs: Long?,
    val isVideo: Boolean,
    val thumbnail: String?,
    val probed: Boolean,
)

/** What a folder walk found; the walk knows nothing about the database. */
data class FoundFile(val uri: String, val name: String, val size: Long, val modifiedAt: Long, val isVideo: Boolean)

data class Playlist(val id: Long, val name: String, val itemCount: Int)

data class PlaylistItem(val id: Long, val playlistId: Long, val position: Int, val uri: String, val title: String)

data class Bookmark(val id: Long, val uri: String, val positionMs: Long, val label: String)

/** A file in a list that's made automatically: favourites, recently played, most played. */
data class SavedTrack(val uri: String, val title: String)

/** Folders, files, playlists and bookmarks, on this phone only. Files are never changed or deleted. */
class LibraryStore(context: Context) :
    SQLiteOpenHelper(context.applicationContext, "library.db", null, SCHEMA_VERSION) {

    override fun onConfigure(db: SQLiteDatabase) {
        db.setForeignKeyConstraintsEnabled(true)
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE folders(id INTEGER PRIMARY KEY, uri TEXT NOT NULL UNIQUE, name TEXT NOT NULL)")
        db.execSQL(
            """CREATE TABLE media(
                id INTEGER PRIMARY KEY,
                uri TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
                size INTEGER NOT NULL DEFAULT 0,
                modified_at INTEGER NOT NULL DEFAULT 0,
                added_at INTEGER NOT NULL,
                duration_ms INTEGER,
                is_video INTEGER NOT NULL DEFAULT 0,
                thumbnail TEXT,
                probed INTEGER NOT NULL DEFAULT 0)""",
        )
        db.execSQL("CREATE INDEX media_folder ON media(folder_id)")
        db.execSQL("CREATE TABLE playlists(id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        db.execSQL(
            """CREATE TABLE playlist_items(
                id INTEGER PRIMARY KEY,
                playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                uri TEXT NOT NULL,
                title TEXT NOT NULL)""",
        )
        db.execSQL("CREATE INDEX playlist_order ON playlist_items(playlist_id, position)")
        db.execSQL(
            """CREATE TABLE bookmarks(
                id INTEGER PRIMARY KEY,
                uri TEXT NOT NULL,
                position_ms INTEGER NOT NULL,
                label TEXT NOT NULL)""",
        )
        db.execSQL("CREATE INDEX bookmark_file ON bookmarks(uri, position_ms)")
        createMusicTables(db)
    }

    // Migration N brings the schema from N-1 to N. Add one here when the schema changes.
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) createMusicTables(db)
    }

    private fun createMusicTables(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE favourites(uri TEXT PRIMARY KEY, title TEXT NOT NULL, added_at INTEGER NOT NULL)")
        db.execSQL(
            """CREATE TABLE plays(
                uri TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                times INTEGER NOT NULL,
                last_played INTEGER NOT NULL)""",
        )
    }

    // ------------------------------------------------------------ folders
    fun addFolder(uri: String, name: String): Long {
        val values = ContentValues().apply {
            put("uri", uri)
            put("name", name)
        }
        val id = writableDatabase.insertWithOnConflict("folders", null, values, SQLiteDatabase.CONFLICT_IGNORE)
        return if (id != -1L) id else folders().first { it.uri == uri }.id
    }

    fun removeFolder(id: Long) {
        writableDatabase.delete("folders", "id = ?", arrayOf(id.toString()))
    }

    fun folders(): List<LibraryFolder> =
        readableDatabase.query("folders", arrayOf("id", "uri", "name"), null, null, null, null, "name COLLATE NOCASE")
            .use { c ->
                buildList {
                    while (c.moveToNext()) add(LibraryFolder(c.getLong(0), c.getString(1), c.getString(2)))
                }
            }

    // -------------------------------------------------------------- media
    /** Makes the folder's rows match a finished walk. Known files keep their details. */
    fun replaceFolderContents(folderId: Long, found: List<FoundFile>, now: Long = System.currentTimeMillis()) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            val known = mutableMapOf<String, Pair<Long, Long>>()
            db.query("media", arrayOf("uri", "size", "modified_at"), "folder_id = ?", arrayOf(folderId.toString()), null, null, null)
                .use { c -> while (c.moveToNext()) known[c.getString(0)] = c.getLong(1) to c.getLong(2) }
            val present = found.mapTo(HashSet()) { it.uri }
            for (uri in known.keys - present) db.delete("media", "uri = ?", arrayOf(uri))
            for (file in found) {
                val values = ContentValues().apply {
                    put("name", file.name)
                    put("size", file.size)
                    put("modified_at", file.modifiedAt)
                    put("is_video", if (file.isVideo) 1 else 0)
                    put("folder_id", folderId)
                }
                val previous = known[file.uri]
                if (previous == null) {
                    values.put("uri", file.uri)
                    values.put("added_at", now)
                    db.insertWithOnConflict("media", null, values, SQLiteDatabase.CONFLICT_IGNORE)
                } else {
                    if (previous != (file.size to file.modifiedAt)) values.put("probed", 0)
                    db.update("media", values, "uri = ?", arrayOf(file.uri))
                }
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun recordProbe(id: Long, durationMs: Long?, thumbnail: String?) {
        val values = ContentValues().apply {
            put("duration_ms", durationMs)
            put("thumbnail", thumbnail)
            put("probed", 1)
        }
        writableDatabase.update("media", values, "id = ?", arrayOf(id.toString()))
    }

    fun unprobed(limit: Int = 200): List<MediaEntry> = queryMedia("probed = 0", null, "id", limit)

    fun media(search: String = "", sort: SortOrder = SortOrder.NAME, recent: Map<String, Long> = emptyMap()): List<MediaEntry> {
        val needle = search.trim().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        val where = if (needle.isEmpty()) null else "name LIKE ? ESCAPE '\\'"
        val args = if (needle.isEmpty()) null else arrayOf("%$needle%")
        val order = when (sort) {
            SortOrder.DATE_ADDED -> "added_at DESC, name COLLATE NOCASE"
            SortOrder.DURATION -> "duration_ms IS NULL, duration_ms DESC, name COLLATE NOCASE"
            SortOrder.SIZE -> "size DESC, name COLLATE NOCASE"
            SortOrder.NAME, SortOrder.RECENTLY_PLAYED -> "name COLLATE NOCASE"
        }
        val rows = queryMedia(where, args, order, null)
        return if (sort == SortOrder.RECENTLY_PLAYED) rows.sortedByDescending { recent[it.uri] ?: 0L } else rows
    }

    /** Pictures in use, so files left behind by removed entries can be deleted. */
    fun thumbnails(): Set<String> =
        readableDatabase.query("media", arrayOf("thumbnail"), "thumbnail IS NOT NULL", null, null, null, null).use { c ->
            buildSet { while (c.moveToNext()) add(c.getString(0)) }
        }

    /** Each file's picture, for screens that list files from elsewhere. */
    fun thumbnailsByFile(): Map<String, String> =
        readableDatabase.query("media", arrayOf("uri", "thumbnail"), "thumbnail IS NOT NULL", null, null, null, null).use { c ->
            buildMap { while (c.moveToNext()) put(c.getString(0), c.getString(1)) }
        }

    private fun queryMedia(where: String?, args: Array<String>?, order: String, limit: Int?): List<MediaEntry> =
        readableDatabase.query(
            "media",
            arrayOf("id", "uri", "name", "folder_id", "size", "added_at", "duration_ms", "is_video", "thumbnail", "probed"),
            where,
            args,
            null,
            null,
            order,
            limit?.toString(),
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        MediaEntry(
                            c.getLong(0),
                            c.getString(1),
                            c.getString(2),
                            c.getLong(3),
                            c.getLong(4),
                            c.getLong(5),
                            if (c.isNull(6)) null else c.getLong(6),
                            c.getInt(7) != 0,
                            c.getString(8),
                            c.getInt(9) != 0,
                        ),
                    )
                }
            }
        }

    // ---------------------------------------------------------- playlists
    fun createPlaylist(name: String): Long =
        writableDatabase.insert("playlists", null, ContentValues().apply { put("name", name) })

    fun renamePlaylist(id: Long, name: String) {
        writableDatabase.update("playlists", ContentValues().apply { put("name", name) }, "id = ?", arrayOf(id.toString()))
    }

    fun deletePlaylist(id: Long) {
        writableDatabase.delete("playlists", "id = ?", arrayOf(id.toString()))
    }

    fun playlists(): List<Playlist> = readableDatabase.rawQuery(
        """SELECT p.id, p.name, COUNT(i.id) FROM playlists p
           LEFT JOIN playlist_items i ON i.playlist_id = p.id
           GROUP BY p.id ORDER BY p.name COLLATE NOCASE""",
        null,
    ).use { c ->
        buildList { while (c.moveToNext()) add(Playlist(c.getLong(0), c.getString(1), c.getInt(2))) }
    }

    fun addToPlaylist(playlistId: Long, uri: String, title: String) {
        val db = writableDatabase
        val position = db.rawQuery(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_items WHERE playlist_id = ?",
            arrayOf(playlistId.toString()),
        ).use { c ->
            c.moveToFirst()
            c.getInt(0)
        }
        db.insert(
            "playlist_items",
            null,
            ContentValues().apply {
                put("playlist_id", playlistId)
                put("position", position)
                put("uri", uri)
                put("title", title)
            },
        )
    }

    fun playlistItems(playlistId: Long): List<PlaylistItem> = readableDatabase.query(
        "playlist_items",
        arrayOf("id", "playlist_id", "position", "uri", "title"),
        "playlist_id = ?",
        arrayOf(playlistId.toString()),
        null,
        null,
        "position",
    ).use { c ->
        buildList {
            while (c.moveToNext()) {
                add(PlaylistItem(c.getLong(0), c.getLong(1), c.getInt(2), c.getString(3), c.getString(4)))
            }
        }
    }

    fun removePlaylistItem(item: PlaylistItem) {
        writableDatabase.delete("playlist_items", "id = ?", arrayOf(item.id.toString()))
    }

    /** Swaps an item with its neighbour; [delta] is -1 for up and +1 for down. */
    fun moveInPlaylist(item: PlaylistItem, delta: Int) {
        val items = playlistItems(item.playlistId)
        val from = items.indexOfFirst { it.id == item.id }
        val other = items.getOrNull(from + delta) ?: return
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.update("playlist_items", ContentValues().apply { put("position", other.position) }, "id = ?", arrayOf(item.id.toString()))
            db.update("playlist_items", ContentValues().apply { put("position", item.position) }, "id = ?", arrayOf(other.id.toString()))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    // ---------------------------------------------------------- favourites and plays
    fun isFavourite(uri: String): Boolean = readableDatabase
        .query("favourites", arrayOf("uri"), "uri = ?", arrayOf(uri), null, null, null)
        .use { it.moveToFirst() }

    fun setFavourite(uri: String, title: String, favourite: Boolean, now: Long = System.currentTimeMillis()) {
        if (!favourite) {
            writableDatabase.delete("favourites", "uri = ?", arrayOf(uri))
            return
        }
        val values = ContentValues().apply {
            put("uri", uri)
            put("title", title)
            put("added_at", now)
        }
        writableDatabase.insertWithOnConflict("favourites", null, values, SQLiteDatabase.CONFLICT_IGNORE)
    }

    fun favourites(): List<SavedTrack> = tracks("favourites", "added_at DESC", null)

    // In two steps: Android 10's SQLite is too old for INSERT ... ON CONFLICT DO UPDATE.
    fun recordPlay(uri: String, title: String, now: Long = System.currentTimeMillis()) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.execSQL(
                "UPDATE plays SET times = times + 1, last_played = ?, title = ? WHERE uri = ?",
                arrayOf<Any>(now, title, uri),
            )
            db.execSQL(
                "INSERT OR IGNORE INTO plays(uri, title, times, last_played) VALUES(?, ?, 1, ?)",
                arrayOf<Any>(uri, title, now),
            )
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun recentlyPlayed(limit: Int = AUTOMATIC_LIST_SIZE): List<SavedTrack> = tracks("plays", "last_played DESC", limit)

    fun mostPlayed(limit: Int = AUTOMATIC_LIST_SIZE): List<SavedTrack> = tracks("plays", "times DESC, last_played DESC", limit)

    fun clearPlays() {
        writableDatabase.delete("plays", null, null)
    }

    private fun tracks(table: String, order: String, limit: Int?): List<SavedTrack> =
        readableDatabase.query(table, arrayOf("uri", "title"), null, null, null, null, order, limit?.toString()).use { c ->
            buildList { while (c.moveToNext()) add(SavedTrack(c.getString(0), c.getString(1))) }
        }

    // ---------------------------------------------------------- bookmarks
    fun addBookmark(uri: String, positionMs: Long, label: String): Long =
        writableDatabase.insert(
            "bookmarks",
            null,
            ContentValues().apply {
                put("uri", uri)
                put("position_ms", positionMs)
                put("label", label)
            },
        )

    fun bookmarks(uri: String): List<Bookmark> = readableDatabase.query(
        "bookmarks",
        arrayOf("id", "uri", "position_ms", "label"),
        "uri = ?",
        arrayOf(uri),
        null,
        null,
        "position_ms",
    ).use { c ->
        buildList { while (c.moveToNext()) add(Bookmark(c.getLong(0), c.getString(1), c.getLong(2), c.getString(3))) }
    }

    fun removeBookmark(id: Long) {
        writableDatabase.delete("bookmarks", "id = ?", arrayOf(id.toString()))
    }

    companion object {
        private const val SCHEMA_VERSION = 2
        const val AUTOMATIC_LIST_SIZE = 50
    }
}
