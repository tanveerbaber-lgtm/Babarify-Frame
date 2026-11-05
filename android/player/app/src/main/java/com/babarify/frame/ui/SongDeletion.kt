package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.app.RecoverableSecurityException
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.widget.Toast
import com.babarify.frame.R
import com.babarify.frame.core.Song
import com.babarify.frame.engine.PlaybackSession

/**
 * Deletes songs from the phone, always after the person confirms: Android 11 and later ask themselves, and
 * on Android 10 this asks first, since Android stays silent about files the app added. The song that's playing
 * is left out. A screen that uses this passes its onActivityResult on to [onResult].
 */
object SongDeletion {
    private const val REQUEST = 4101

    private class Pending(val songs: List<Song>, val remaining: List<Song>, val onDeleted: (List<Song>) -> Unit)

    private var pending: Pending? = null

    fun ask(activity: Activity, songs: List<Song>, onDeleted: (List<Song>) -> Unit) {
        val playing = PlaybackSession.get(activity).mediaUri?.toString()
        val deletable = songs.filter { it.uri != playing }
        if (deletable.size < songs.size) {
            Toast.makeText(activity, R.string.delete_not_playing, Toast.LENGTH_LONG).show()
        }
        if (deletable.isEmpty()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val request = MediaStore.createDeleteRequest(activity.contentResolver, deletable.map { Uri.parse(it.uri) })
            pending = Pending(deletable, emptyList(), onDeleted)
            activity.startIntentSenderForResult(request.intentSender, REQUEST, null, 0, 0, 0)
            return
        }
        AlertDialog.Builder(activity)
            .setTitle(activity.resources.getQuantityString(R.plurals.delete_question, deletable.size, deletable.size))
            .setMessage(R.string.delete_explanation)
            .setPositiveButton(R.string.delete) { _, _ -> deleteOneByOne(activity, deletable, deletable, onDeleted) }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    /** Android 10 asks about a file that isn't the app's own when deleting it fails with this exception. */
    private fun deleteOneByOne(
        activity: Activity,
        songs: List<Song>,
        remaining: List<Song>,
        onDeleted: (List<Song>) -> Unit,
    ) {
        for ((index, song) in remaining.withIndex()) {
            try {
                activity.contentResolver.delete(Uri.parse(song.uri), null, null)
            } catch (needed: RecoverableSecurityException) {
                pending = Pending(songs, remaining.drop(index), onDeleted)
                activity.startIntentSenderForResult(needed.userAction.actionIntent.intentSender, REQUEST, null, 0, 0, 0)
                return
            } catch (_: SecurityException) {
                Toast.makeText(activity, R.string.delete_failed, Toast.LENGTH_LONG).show()
                finished(activity, songs - remaining.drop(index).toSet(), onDeleted)
                return
            }
        }
        finished(activity, songs, onDeleted)
    }

    fun onResult(activity: Activity, requestCode: Int, resultCode: Int, @Suppress("UNUSED_PARAMETER") data: Intent?) {
        if (requestCode != REQUEST) return
        val waiting = pending ?: return
        pending = null
        val done = waiting.songs - waiting.remaining.toSet()
        when {
            resultCode != Activity.RESULT_OK -> if (done.isNotEmpty()) finished(activity, done, waiting.onDeleted)
            waiting.remaining.isEmpty() -> finished(activity, waiting.songs, waiting.onDeleted)
            else -> deleteOneByOne(activity, waiting.songs, waiting.remaining, waiting.onDeleted)
        }
    }

    private fun finished(activity: Activity, deleted: List<Song>, onDeleted: (List<Song>) -> Unit) {
        val session = PlaybackSession.get(activity)
        val uris = deleted.map { it.uri }.toSet()
        session.removeFromQueue(uris)
        session.preferences.hiddenSongs = session.preferences.hiddenSongs - uris
        onDeleted(deleted)
        if (deleted.isNotEmpty()) {
            val message = activity.resources.getQuantityString(R.plurals.deleted_count, deleted.size, deleted.size)
            Toast.makeText(activity, message, Toast.LENGTH_SHORT).show()
        }
    }
}
