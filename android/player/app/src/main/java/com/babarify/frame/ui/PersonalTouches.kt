package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.LayerDrawable
import android.media.RingtoneManager
import android.net.Uri
import android.provider.Settings
import android.widget.Toast
import com.babarify.frame.R
import com.babarify.frame.core.Song
import java.io.File

/** Sets a song as the phone's ringtone, after asking. Android needs its own permission for that. */
object Ringtone {
    fun ask(activity: Activity, song: Song) {
        if (!Settings.System.canWrite(activity)) {
            AlertDialog.Builder(activity)
                .setTitle(R.string.set_as_ringtone)
                .setMessage(R.string.ringtone_permission)
                .setPositiveButton(R.string.open_settings) { _, _ ->
                    activity.startActivity(
                        Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:${activity.packageName}")),
                    )
                }
                .setNegativeButton(android.R.string.cancel, null)
                .show()
            return
        }
        AlertDialog.Builder(activity)
            .setTitle(R.string.set_as_ringtone)
            .setMessage(activity.getString(R.string.ringtone_question, song.title))
            .setPositiveButton(R.string.set_as_ringtone) { _, _ -> set(activity, song) }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun set(activity: Activity, song: Song) {
        val message = try {
            RingtoneManager.setActualDefaultRingtoneUri(activity, RingtoneManager.TYPE_RINGTONE, Uri.parse(song.uri))
            R.string.ringtone_set
        } catch (_: RuntimeException) {
            R.string.ringtone_not_set
        }
        Toast.makeText(activity, message, Toast.LENGTH_LONG).show()
    }
}

/** A picture of the person's own behind the main screens, dimmed so the text stays readable. */
object PictureBackground {
    private const val MAX_SIZE = 1600
    private const val DIMMING = 0.78f
    private var picture: Bitmap? = null
    private var loadedStamp = 0L

    fun file(context: Context) = File(context.filesDir, "background_picture")

    fun set(context: Context, source: Uri) {
        context.contentResolver.openInputStream(source)?.use { input ->
            file(context).outputStream().use { input.copyTo(it) }
        }
        loadedStamp = 0
    }

    fun remove(context: Context) {
        file(context).delete()
        picture = null
        loadedStamp = 0
    }

    fun apply(activity: Activity) {
        val source = file(activity)
        if (!source.isFile) return
        if (loadedStamp != source.lastModified()) {
            picture = decode(source)
            loadedStamp = source.lastModified()
        }
        val bitmap = picture ?: return
        val colour = activity.themeColor(R.attr.bgColor)
        val dim = ColorDrawable((colour and 0x00FFFFFF) or ((DIMMING * 255).toInt() shl 24))
        val image = BitmapDrawable(activity.resources, bitmap).apply { gravity = android.view.Gravity.FILL }
        activity.window.setBackgroundDrawable(LayerDrawable(arrayOf(image, dim)))
    }

    private fun decode(source: File): Bitmap? {
        val size = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(source.path, size)
        var sample = 1
        while (maxOf(size.outWidth, size.outHeight) / sample > MAX_SIZE) sample *= 2
        return BitmapFactory.decodeFile(source.path, BitmapFactory.Options().apply { inSampleSize = sample })
    }
}
