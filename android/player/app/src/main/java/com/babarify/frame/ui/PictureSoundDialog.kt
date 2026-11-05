package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.TextView
import com.babarify.frame.R
import com.babarify.frame.core.EnhancementProfile
import com.babarify.frame.core.PictureSettings
import com.babarify.frame.data.Preferences
import com.babarify.frame.engine.PlayerEngine
import kotlin.math.roundToInt

/** Brightness, colour and the equalizer, as on desktop's Picture & Sound panel. Changes apply at once. */
object PictureSoundDialog {
    fun show(
        activity: Activity,
        preferences: Preferences,
        engine: PlayerEngine?,
        onPicture: () -> Unit,
        onEqualizer: () -> Unit,
    ) {
        val form = Form(activity, preferences, engine, onPicture, onEqualizer)
        AlertDialog.Builder(activity)
            .setTitle(R.string.picture_and_sound)
            .setView(ScrollView(activity).apply { addView(form.root) })
            .setPositiveButton(android.R.string.ok, null)
            .setNeutralButton(R.string.profiles) { _, _ -> showProfiles(activity, preferences, onPicture, onEqualizer) }
            .show()
    }

    private fun showProfiles(activity: Activity, preferences: Preferences, onPicture: () -> Unit, onEqualizer: () -> Unit) {
        val profiles = preferences.profiles
        val builder = AlertDialog.Builder(activity)
            .setTitle(R.string.profiles)
            .setPositiveButton(R.string.save_profile) { _, _ -> askProfileName(activity, preferences) }
            .setNegativeButton(android.R.string.cancel, null)
        if (profiles.isEmpty()) {
            builder.setMessage(R.string.no_profiles).show()
            return
        }
        builder.setItems(profiles.map { it.name }.toTypedArray()) { _, which ->
            preferences.picture = profiles[which].picture
            preferences.equalizer = profiles[which].equalizer
            onPicture()
            onEqualizer()
        }
        val dialog = builder.show()
        dialog.listView.setOnItemLongClickListener { _, _, which, _ ->
            preferences.profiles = profiles.filterIndexed { index, _ -> index != which }
            dialog.dismiss()
            true
        }
    }

    private fun askProfileName(activity: Activity, preferences: Preferences) {
        val input = EditText(activity).apply { hint = activity.getString(R.string.profile_name) }
        AlertDialog.Builder(activity)
            .setTitle(R.string.save_profile)
            .setView(input)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                val name = input.text.toString().trim().take(EnhancementProfile.MAX_NAME)
                if (name.isNotEmpty()) {
                    val others = preferences.profiles.filter { it.name != name }
                    preferences.profiles = (others + EnhancementProfile(name, preferences.picture, preferences.equalizer))
                        .takeLast(EnhancementProfile.MAX_PROFILES)
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private class Form(
        private val activity: Activity,
        private val preferences: Preferences,
        private val engine: PlayerEngine?,
        private val onPicture: () -> Unit,
        private val onEqualizer: () -> Unit,
    ) {
        val root = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            val padding = (20 * activity.resources.displayMetrics.density).toInt()
            setPadding(padding, padding / 2, padding, padding / 2)
        }
        private val resettable = ArrayList<() -> Unit>()

        init {
            val picture = preferences.picture
            pictureSlider(R.string.brightness, picture.brightness, 0f, 2f) { p, v -> p.copy(brightness = v) }
            pictureSlider(R.string.contrast, picture.contrast, 0f, 2f) { p, v -> p.copy(contrast = v) }
            pictureSlider(R.string.saturation, picture.saturation, 0f, 3f) { p, v -> p.copy(saturation = v) }
            pictureSlider(R.string.hue, picture.hue, -180f, 180f) { p, v -> p.copy(hue = v) }
            root.addView(
                Button(activity).apply {
                    setText(R.string.reset_picture)
                    setOnClickListener {
                        preferences.picture = PictureSettings()
                        onPicture()
                        resettable.forEach { it() }
                    }
                },
            )
            equalizerSection()
        }

        private fun pictureSlider(
            label: Int,
            value: Float,
            low: Float,
            high: Float,
            apply: (PictureSettings, Float) -> PictureSettings,
        ) {
            val default = apply(PictureSettings(), value).let { if (label == R.string.hue) 0f else 1f }
            val update = slider(activity.getString(label), value, low, high) { v ->
                preferences.picture = apply(preferences.picture, v).normalized()
                onPicture()
            }
            resettable.add { update(default) }
        }

        private fun equalizerSection() {
            root.addView(
                Button(activity).apply {
                    setText(R.string.equalizer)
                    setOnClickListener { EqualizerPanel.show(activity, preferences, engine, onEqualizer) }
                },
            )
        }

        /** Returns a way to move the slider from code, without counting as the user's change. */
        private fun slider(label: String, value: Float, low: Float, high: Float, onChange: (Float) -> Unit): (Float) -> Unit {
            val title = TextView(activity).apply {
                setTextAppearance(R.style.Text_Muted)
            }
            val bar = SeekBar(activity).apply {
                contentDescription = label
                max = STEPS
                progress = (((value - low) / (high - low)) * STEPS).roundToInt()
            }
            fun show(v: Float) {
                title.text = "$label: ${"%.2f".format(v)}"
            }
            show(value)
            bar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(seek: SeekBar, progress: Int, fromUser: Boolean) {
                    val v = low + (high - low) * progress / STEPS
                    show(v)
                    if (fromUser) onChange(v)
                }

                override fun onStartTrackingTouch(seek: SeekBar) = Unit
                override fun onStopTrackingTouch(seek: SeekBar) = Unit
            })
            root.addView(title)
            root.addView(bar)
            return { v -> bar.progress = (((v - low) / (high - low)) * STEPS).roundToInt() }
        }
    }

    private const val STEPS = 100
}
