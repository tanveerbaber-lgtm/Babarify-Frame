package com.babarify.frame.data

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.MediaStore
import com.babarify.frame.core.MusicRules
import com.babarify.frame.core.Song

/** Songs from Android's own media index. Read only, and only after the user allows it. Stays on the phone. */
object MusicLibrary {
    val permission: String
        get() = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.READ_MEDIA_AUDIO
        } else {
            Manifest.permission.READ_EXTERNAL_STORAGE
        }

    fun allowed(context: Context): Boolean =
        context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED

    /** Slow on a big collection: call away from the main thread. Empty if the permission is missing. */
    fun songs(context: Context): List<Song> {
        if (!allowed(context)) return emptyList()
        val collection = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        val columns = arrayOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.ALBUM,
            MediaStore.Audio.Media.ALBUM_ID,
            MediaStore.Audio.Media.RELATIVE_PATH,
            MediaStore.Audio.Media.DISPLAY_NAME,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.DATE_ADDED,
        )
        return try {
            context.contentResolver.query(collection, columns, "${MediaStore.Audio.Media.IS_MUSIC} != 0", null, null)
                ?.use { row ->
                    buildList {
                        while (row.moveToNext()) {
                            val fileName = row.getString(6).orEmpty()
                            add(
                                Song(
                                    uri = ContentUris.withAppendedId(collection, row.getLong(0)).toString(),
                                    title = MusicRules.tagOrNull(row.getString(1)) ?: MusicRules.withoutExtension(fileName),
                                    artist = MusicRules.tagOrNull(row.getString(2)),
                                    album = MusicRules.tagOrNull(row.getString(3)),
                                    albumId = row.getLong(4),
                                    folder = MusicRules.folderName(row.getString(5)),
                                    fileName = fileName,
                                    durationMs = row.getLong(7),
                                    addedAt = row.getLong(8),
                                ),
                            )
                        }
                    }
                }.orEmpty()
        } catch (_: SecurityException) {
            emptyList() // The permission was taken back at this moment.
        }
    }
}
