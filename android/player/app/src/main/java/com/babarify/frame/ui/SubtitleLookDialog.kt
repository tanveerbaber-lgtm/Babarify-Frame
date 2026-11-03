package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.ArrayAdapter
import android.widget.TextView
import com.babarify.frame.R
import com.babarify.frame.core.SubtitleStyle
import com.babarify.frame.data.Preferences

/** Size, colour and background of plain-text subtitles. Files with their own styling keep it. */
object SubtitleLookDialog {
    private val COLOURS = listOf(
        R.string.colour_white to 0xFFFFFF,
        R.string.colour_yellow to 0xFFFF00,
        R.string.colour_green to 0x00FF00,
        R.string.colour_cyan to 0x00FFFF,
    )

    fun show(activity: Activity, preferences: Preferences, onChanged: () -> Unit) {
        val style = preferences.subtitleStyle
        val density = activity.resources.displayMetrics.density
        val root = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            val padding = (20 * density).toInt()
            setPadding(padding, padding / 2, padding, padding / 2)
        }
        fun labelled(text: Int) = TextView(activity).apply {
            setTextAppearance(R.style.Text_Muted)
            setText(text)
            root.addView(this)
        }
        val sizeLabel = labelled(R.string.subtitle_size)
        val size = SeekBar(activity).apply {
            max = 150
            progress = style.sizePct - 50
            contentDescription = activity.getString(R.string.subtitle_size)
        }
        root.addView(size)
        labelled(R.string.subtitle_colour)
        val colour = Spinner(activity).apply {
            adapter = ArrayAdapter(
                activity,
                android.R.layout.simple_spinner_dropdown_item,
                COLOURS.map { activity.getString(it.first) },
            )
            setSelection(COLOURS.indexOfFirst { it.second == style.textColor }.coerceAtLeast(0))
            contentDescription = activity.getString(R.string.subtitle_colour)
        }
        root.addView(colour)
        val backgroundLabel = labelled(R.string.subtitle_background)
        val background = SeekBar(activity).apply {
            max = 100
            progress = style.backgroundOpacity
            contentDescription = activity.getString(R.string.subtitle_background)
        }
        root.addView(background)

        fun refresh() {
            sizeLabel.text = activity.getString(R.string.subtitle_size_level, size.progress + 50)
            backgroundLabel.text = activity.getString(R.string.subtitle_background_level, background.progress)
        }
        val listener = object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(bar: SeekBar, progress: Int, fromUser: Boolean) = refresh()
            override fun onStartTrackingTouch(bar: SeekBar) = Unit
            override fun onStopTrackingTouch(bar: SeekBar) = Unit
        }
        size.setOnSeekBarChangeListener(listener)
        background.setOnSeekBarChangeListener(listener)
        refresh()

        AlertDialog.Builder(activity)
            .setTitle(R.string.subtitle_look)
            .setView(root)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                preferences.subtitleStyle = SubtitleStyle(
                    size.progress + 50,
                    COLOURS[colour.selectedItemPosition].second,
                    background.progress,
                ).normalized()
                onChanged()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }
}
