package com.babarify.frame.data

import android.content.Context
import android.net.Uri
import com.babarify.frame.core.Song
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/**
 * Corrections to a song's title, artist and album, and its cover. They're kept by the app; the song's own
 * file isn't changed, so other apps still see its original tags.
 */
class SongEdits(context: Context) {
    private val appContext = context.applicationContext
    private val store = appContext.getSharedPreferences("song_edits", Context.MODE_PRIVATE)

    data class Edit(val title: String?, val artist: String?, val album: String?)

    fun get(uri: String): Edit? {
        val raw = store.getString(uri, null) ?: return null
        val json = JSONObject(raw)
        return Edit(text(json, "title"), text(json, "artist"), text(json, "album"))
    }

    /** A blank value goes back to what the file says. */
    fun set(uri: String, title: String, artist: String, album: String) {
        val json = JSONObject().put("title", title.trim()).put("artist", artist.trim()).put("album", album.trim())
        store.edit().putString(uri, json.toString()).apply()
    }

    fun applied(song: Song): Song {
        val edit = get(song.uri) ?: return song
        return song.copy(
            title = edit.title ?: song.title,
            artist = edit.artist ?: song.artist,
            album = edit.album ?: song.album,
        )
    }

    fun coverFile(uri: String): File {
        val hash = MessageDigest.getInstance("SHA-256").digest(uri.toByteArray())
        return File(File(appContext.filesDir, "covers"), hash.take(16).joinToString("") { "%02x".format(it) })
    }

    /** Copies the picture, so it stays if the original is moved or deleted. */
    fun setCover(uri: String, picture: Uri) {
        val target = coverFile(uri)
        target.parentFile?.mkdirs()
        appContext.contentResolver.openInputStream(picture)?.use { input ->
            target.outputStream().use { input.copyTo(it) }
        }
    }

    private fun text(json: JSONObject, key: String): String? = json.optString(key).takeIf { it.isNotBlank() }
}
