package com.babarify.frame.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

data class HistoryEntry(
    val uri: String,
    val title: String,
    val positionMs: Long,
    val durationMs: Long?,
    val finished: Boolean,
)

/**
 * Recent files, on this device only. Fields follow the desktop `history` table, but the key is the
 * `content:` address because Android gives no reliable path (M12 shared contracts).
 */
class HistoryStore(context: Context) :
    SQLiteOpenHelper(context.applicationContext, "history.db", null, SCHEMA_VERSION) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE history(
                uri TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                position_ms INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER,
                finished INTEGER NOT NULL DEFAULT 0,
                last_played_at INTEGER NOT NULL)""",
        )
        db.execSQL("CREATE INDEX history_recent ON history(last_played_at DESC)")
    }

    // Migration N brings the schema from N-1 to N. Add one here when the schema changes.
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    fun save(entry: HistoryEntry, playedAt: Long = System.currentTimeMillis()) {
        val values = ContentValues().apply {
            put("uri", entry.uri)
            put("title", entry.title)
            put("position_ms", entry.positionMs)
            put("duration_ms", entry.durationMs)
            put("finished", if (entry.finished) 1 else 0)
            put("last_played_at", playedAt)
        }
        writableDatabase.insertWithOnConflict("history", null, values, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun find(uri: String): HistoryEntry? = query("uri = ?", arrayOf(uri), 1).firstOrNull()

    fun recent(limit: Int = RECENT_LIMIT): List<HistoryEntry> = query(null, null, limit)

    fun remove(uri: String) {
        writableDatabase.delete("history", "uri = ?", arrayOf(uri))
    }

    fun clear() {
        writableDatabase.delete("history", null, null)
    }

    private fun query(where: String?, args: Array<String>?, limit: Int): List<HistoryEntry> =
        readableDatabase.query(
            "history",
            arrayOf("uri", "title", "position_ms", "duration_ms", "finished"),
            where,
            args,
            null,
            null,
            "last_played_at DESC",
            limit.toString(),
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) {
                    add(
                        HistoryEntry(
                            uri = cursor.getString(0),
                            title = cursor.getString(1),
                            positionMs = cursor.getLong(2),
                            durationMs = if (cursor.isNull(3)) null else cursor.getLong(3),
                            finished = cursor.getInt(4) != 0,
                        ),
                    )
                }
            }
        }

    private companion object {
        const val SCHEMA_VERSION = 1
        const val RECENT_LIMIT = 50
    }
}
