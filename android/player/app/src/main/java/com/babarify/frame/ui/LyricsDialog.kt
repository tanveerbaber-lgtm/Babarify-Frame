package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.graphics.Typeface
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.babarify.frame.R
import com.babarify.frame.core.Lyrics
import com.babarify.frame.engine.PlaybackSession
import java.io.File
import java.io.IOException
import java.security.MessageDigest

/** Lyrics saved on this phone, one file per song. */
object LyricsStore {
    private fun file(context: Context, uri: String): File {
        val hash = MessageDigest.getInstance("SHA-256").digest(uri.toByteArray())
        val name = hash.take(16).joinToString("") { "%02x".format(it) }
        return File(File(context.filesDir, "lyrics"), "$name.lrc")
    }

    fun load(context: Context, uri: String): String? = try {
        file(context, uri).takeIf { it.isFile }?.readText()
    } catch (_: IOException) {
        null
    }

    fun save(context: Context, uri: String, text: String) {
        val target = file(context, uri)
        target.parentFile?.mkdirs()
        target.writeText(text)
    }
}

object LyricsDialog {
    private const val FOLLOW_MS = 250L

    fun show(activity: Activity, session: PlaybackSession, onLoadFile: () -> Unit) {
        val uri = session.mediaUri?.toString() ?: return
        val lines = Lyrics.parse(LyricsStore.load(activity, uri).orEmpty())
        val density = activity.resources.displayMetrics.density
        val column = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding((24 * density).toInt(), (16 * density).toInt(), (24 * density).toInt(), 0)
        }
        val rows = lines.map { line ->
            TextView(activity).apply {
                text = line.text
                gravity = Gravity.CENTER
                textSize = 17f
                setPadding(0, (6 * density).toInt(), 0, (6 * density).toInt())
                setTextColor(activity.themeColor(R.attr.inkMutedColor))
            }.also(column::addView)
        }
        if (lines.isEmpty()) {
            column.addView(
                TextView(activity).apply {
                    setText(R.string.no_lyrics)
                    setTextColor(activity.themeColor(R.attr.inkMutedColor))
                },
            )
        }
        val scroll = ScrollView(activity).apply { addView(column) }
        val handler = Handler(Looper.getMainLooper())
        var shown = -1
        val follow = object : Runnable {
            override fun run() {
                val index = Lyrics.currentLine(lines, session.positionMs)
                if (index != shown) {
                    rows.getOrNull(shown)?.apply {
                        setTypeface(null, Typeface.NORMAL)
                        setTextColor(activity.themeColor(R.attr.inkMutedColor))
                    }
                    rows.getOrNull(index)?.apply {
                        setTypeface(null, Typeface.BOLD)
                        setTextColor(activity.themeColor(R.attr.accent2Color))
                        scroll.smoothScrollTo(0, (top - scroll.height / 2 + height / 2).coerceAtLeast(0))
                    }
                    shown = index
                }
                handler.postDelayed(this, FOLLOW_MS)
            }
        }
        AlertDialog.Builder(activity)
            .setTitle(R.string.lyrics)
            .setView(scroll)
            .setPositiveButton(R.string.lyrics_load) { _, _ -> onLoadFile() }
            .setNeutralButton(R.string.lyrics_type) { _, _ -> type(activity, session, onLoadFile) }
            .setNegativeButton(R.string.close, null)
            .setOnDismissListener { handler.removeCallbacks(follow) }
            .show()
        handler.post(follow)
    }

    private fun type(activity: Activity, session: PlaybackSession, onLoadFile: () -> Unit) {
        val uri = session.mediaUri?.toString() ?: return
        val box = EditText(activity).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            minLines = 8
            gravity = Gravity.TOP
            setText(LyricsStore.load(activity, uri).orEmpty())
        }
        AlertDialog.Builder(activity)
            .setTitle(R.string.lyrics_type)
            .setView(box)
            .setPositiveButton(R.string.save) { _, _ ->
                LyricsStore.save(activity, uri, box.text.toString())
                show(activity, session, onLoadFile)
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }
}
