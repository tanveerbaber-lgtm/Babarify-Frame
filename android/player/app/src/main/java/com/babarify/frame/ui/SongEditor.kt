package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import com.babarify.frame.R
import com.babarify.frame.core.Song
import com.babarify.frame.data.SongEdits
import java.io.IOException

/** Corrects a song's details in the app. The file itself isn't changed. */
object SongEditor {
    private const val REQUEST_COVER = 4102
    private var waitingForCover: Song? = null

    fun show(activity: Activity, song: Song) {
        val edits = SongEdits(activity)
        val shown = edits.applied(song)
        val density = activity.resources.displayMetrics.density
        fun field(hint: Int, value: String?) = EditText(activity).apply {
            setHint(hint)
            setText(value.orEmpty())
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
        }
        val title = field(R.string.tag_title, shown.title)
        val artist = field(R.string.tag_artist, shown.artist)
        val album = field(R.string.tag_album, shown.album)
        val form = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            val side = (24 * density).toInt()
            setPadding(side, (8 * density).toInt(), side, 0)
            addView(title)
            addView(artist)
            addView(album)
        }
        AlertDialog.Builder(activity)
            .setTitle(R.string.edit_details)
            .setMessage(R.string.edit_details_note)
            .setView(form)
            .setPositiveButton(R.string.save) { _, _ ->
                edits.set(song.uri, title.text.toString(), artist.text.toString(), album.text.toString())
                activity.recreate()
            }
            .setNeutralButton(R.string.change_cover) { _, _ -> pickCover(activity, song) }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun pickCover(activity: Activity, song: Song) {
        waitingForCover = song
        val pick = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "image/*"
        }
        @Suppress("DEPRECATION")
        activity.startActivityForResult(pick, REQUEST_COVER)
    }

    fun onResult(activity: Activity, requestCode: Int, resultCode: Int, picture: Uri?) {
        if (requestCode != REQUEST_COVER) return
        val song = waitingForCover ?: return
        waitingForCover = null
        if (resultCode != Activity.RESULT_OK || picture == null) return
        try {
            SongEdits(activity).setCover(song.uri, picture)
            Art.forgetPictures()
            activity.recreate()
        } catch (_: IOException) {
            Toast.makeText(activity, R.string.cover_not_saved, Toast.LENGTH_LONG).show()
        }
    }
}
