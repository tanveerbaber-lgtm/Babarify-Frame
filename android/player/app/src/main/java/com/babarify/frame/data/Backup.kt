package com.babarify.frame.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.InputStream
import java.io.OutputStream

/**
 * A file holding settings and lists, to keep safe. Playlists, favourites and hidden songs are in it; history
 * isn't, so it says less about what was played. Restoring adds to the lists; it never removes anything.
 */
object Backup {
    private const val FORMAT = "babarify-backup"
    private const val VERSION = 1

    class Unusable(val reason: Reason) : Exception()

    enum class Reason { NOT_A_BACKUP, TOO_NEW }

    data class Restored(val playlists: Int, val favourites: Int)

    fun write(context: Context, out: OutputStream) {
        val json = LibraryStore(context).use { store ->
            JSONObject()
                .put("format", FORMAT)
                .put("version", VERSION)
                .put("preferences", Preferences(context).exported())
                .put(
                    "playlists",
                    JSONArray(
                        store.playlists().map { playlist ->
                            JSONObject()
                                .put("name", playlist.name)
                                .put("items", JSONArray(store.playlistItems(playlist.id).map { track(it.uri, it.title) }))
                        },
                    ),
                )
                .put("favourites", JSONArray(store.favourites().map { track(it.uri, it.title) }))
        }
        out.write(json.toString(2).toByteArray())
    }

    fun restore(context: Context, input: InputStream): Restored {
        val json = try {
            JSONObject(input.readBytes().toString(Charsets.UTF_8))
        } catch (_: JSONException) {
            throw Unusable(Reason.NOT_A_BACKUP)
        }
        if (json.optString("format") != FORMAT) throw Unusable(Reason.NOT_A_BACKUP)
        if (json.optInt("version", Int.MAX_VALUE) > VERSION) throw Unusable(Reason.TOO_NEW)
        json.optJSONObject("preferences")?.let { Preferences(context).restore(it) }
        return LibraryStore(context).use { store ->
            val existing = store.playlists().associate { it.name to it.id }
            var playlists = 0
            objects(json.optJSONArray("playlists")).forEach { entry ->
                val name = entry.optString("name")
                if (name.isBlank()) return@forEach
                val id = existing[name] ?: store.createPlaylist(name).also { playlists++ }
                val have = store.playlistItems(id).map { it.uri }.toSet()
                objects(entry.optJSONArray("items")).forEach { item ->
                    val uri = item.optString("uri")
                    if (uri.isNotEmpty() && uri !in have) store.addToPlaylist(id, uri, item.optString("title"))
                }
            }
            var favourites = 0
            objects(json.optJSONArray("favourites")).forEach { item ->
                val uri = item.optString("uri")
                if (uri.isNotEmpty() && !store.isFavourite(uri)) {
                    store.setFavourite(uri, item.optString("title"), true)
                    favourites++
                }
            }
            Restored(playlists, favourites)
        }
    }

    private fun track(uri: String, title: String) = JSONObject().put("uri", uri).put("title", title)

    private fun objects(array: JSONArray?): List<JSONObject> =
        (0 until (array?.length() ?: 0)).mapNotNull { array?.optJSONObject(it) }
}
