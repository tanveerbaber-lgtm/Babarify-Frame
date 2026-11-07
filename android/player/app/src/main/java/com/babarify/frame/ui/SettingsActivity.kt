package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import com.babarify.frame.R
import com.babarify.frame.core.MusicRules
import com.babarify.frame.core.LeaveAction
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.data.Backup
import com.babarify.frame.data.HistoryStore
import com.babarify.frame.data.LibraryStore
import com.babarify.frame.data.MusicLibrary
import com.babarify.frame.data.Preferences
import com.babarify.frame.engine.PlaybackSession

class SettingsActivity : Activity() {
    private lateinit var preferences: Preferences
    private lateinit var session: PlaybackSession
    private lateinit var form: LinearLayout
    private lateinit var card: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        session = PlaybackSession.get(this)
        preferences = session.preferences
        form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(20), dp(16), dp(16))
        }
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(
            ScrollView(this).apply { addView(form) },
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f),
        )
        val nav = LinearLayout(this, null, 0, R.style.NavBar)
        root.addView(nav, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(64)))
        BottomNav.attach(this, nav)
        setContentView(root)
        applySystemBarPadding(root)
        build()
    }

    private fun build() {
        form.removeAllViews()
        form.addView(
            TextView(this).apply {
                setTextAppearance(R.style.Text_Title)
                setText(R.string.settings)
            },
        )
        section(R.string.section_appearance)
        choice(getString(R.string.colour_theme, getString(ColourThemes.current(preferences).label))) {
            val themes = ColourThemes.ALL
            pick(themes.map { getString(it.label) }, themes.indexOf(ColourThemes.current(preferences))) { which ->
                preferences.colourTheme = themes[which].key
                recreate()
            }
        }

        val visualLabel = VISUAL_STYLES.first { it.first == preferences.visualStyle }.second
        choice(getString(R.string.animation_style_value, getString(visualLabel))) {
            pick(VISUAL_STYLES.map { getString(it.second) }, VISUAL_STYLES.indexOfFirst { it.first == preferences.visualStyle }) { which ->
                preferences.visualStyle = VISUAL_STYLES[which].first
                build()
            }
        }

        choice(getString(R.string.background_picture)) { chooseBackground() }

        section(R.string.section_playback)
        check(R.string.hardware_decoding, preferences.hardwareDecoding) { preferences.hardwareDecoding = it }
        check(R.string.resume_playback, preferences.resumePlayback) { preferences.resumePlayback = it }
        check(R.string.seek_previews, preferences.seekPreviews) { preferences.seekPreviews = it }
        check(R.string.gestures, preferences.gestures) { preferences.gestures = it }
        val fades = MusicRules.FADE_CHOICES_S
        fun fadeLabel(seconds: Int) = if (seconds == 0) getString(R.string.off) else getString(R.string.seconds, seconds)
        choice(getString(R.string.fade_value, fadeLabel(preferences.fadeSeconds))) {
            pick(fades.map(::fadeLabel), fades.indexOf(preferences.fadeSeconds)) { which ->
                preferences.fadeSeconds = fades[which]
                build()
            }
        }
        val effects = MusicRules.AUDIO_EFFECTS.keys.toList()
        val effectLabels = listOf(R.string.effect_none, R.string.effect_room, R.string.effect_wide, R.string.effect_both)
        choice(getString(R.string.effect_value, getString(effectLabels[effects.indexOf(preferences.audioEffect)]))) {
            pick(effectLabels.map(::getString), effects.indexOf(preferences.audioEffect)) { which ->
                preferences.audioEffect = effects[which]
                Toast.makeText(this, R.string.effect_from_next, Toast.LENGTH_SHORT).show()
                build()
            }
        }
        choice(getString(R.string.seek_step, preferences.seekStepSeconds)) {
            val steps = PlaybackRules.SEEK_STEPS_S
            pick(steps.map { getString(R.string.seek_step, it) }, steps.indexOf(preferences.seekStepSeconds)) { which ->
                preferences.seekStepSeconds = steps[which]
                build()
            }
        }

        section(R.string.section_leaving)
        leaveChoices()

        section(R.string.section_sound)
        check(R.string.remember_volume, preferences.rememberVolume) { preferences.rememberVolume = it }
        check(R.string.allow_boost, preferences.allowVolumeBoost) {
            preferences.allowVolumeBoost = it
            session.onPreferencesChanged()
        }
        note(R.string.allow_boost_note)

        section(R.string.section_subtitles)
        check(R.string.subtitles_auto, preferences.subtitlesAuto) { preferences.subtitlesAuto = it }
        language(R.string.preferred_audio, preferences.preferredAudioLanguage) { preferences.preferredAudioLanguage = it }
        language(R.string.preferred_subtitle, preferences.preferredSubtitleLanguage) { preferences.preferredSubtitleLanguage = it }
        choice(getString(R.string.subtitle_look)) { SubtitleLookDialog.show(this, preferences) { } }

        section(R.string.section_privacy)
        check(R.string.remember_history, preferences.rememberHistory) { preferences.rememberHistory = it }
        choice(getString(R.string.hidden_songs)) { chooseHiddenSongs() }
        choice(getString(R.string.clear_recent)) { clearRecent() }

        section(R.string.section_backup)
        choice(getString(R.string.backup_create)) { pickBackupFile() }
        choice(getString(R.string.backup_restore)) { pickRestoreFile() }

        section(R.string.about)
        choice(getString(R.string.about)) { startActivity(Intent(this, AboutActivity::class.java)) }
        choice(getString(R.string.report_problem)) { showReport() }
        choice(getString(R.string.reset_defaults)) {
            AlertDialog.Builder(this)
                .setMessage(R.string.reset_defaults_question)
                .setPositiveButton(R.string.reset) { _, _ ->
                    preferences.resetToDefaults()
                    session.onPreferencesChanged()
                    build()
                }
                .setNegativeButton(android.R.string.cancel, null)
                .show()
        }
    }

    private fun leaveChoices() {
        val choices = listOf(
            LeaveAction.STOP to R.string.leave_stop,
            LeaveAction.AUDIO to R.string.leave_audio,
            LeaveAction.PICTURE to R.string.leave_picture,
        )
        val group = RadioGroup(this).apply { setPadding(dp(12), dp(4), dp(12), 0) }
        for ((action, label) in choices) {
            group.addView(
                RadioButton(this).apply {
                    id = action.ordinal + 1
                    setText(label)
                    minHeight = dp(48)
                },
            )
        }
        group.check(preferences.leaveAction.ordinal + 1)
        group.setOnCheckedChangeListener { _, checked -> preferences.leaveAction = LeaveAction.entries[checked - 1] }
        card.addView(group)
        note(R.string.leave_note)
    }

    private fun language(label: Int, current: String, onPick: (String) -> Unit) {
        val languages = PlaybackRules.LANGUAGES
        choice(getString(label, languages[current].orEmpty())) {
            val keys = languages.keys.toList()
            pick(keys.map { languages[it].orEmpty() }, keys.indexOf(current)) { which ->
                onPick(keys[which])
                build()
            }
        }
    }

    private fun chooseBackground() {
        if (!PictureBackground.file(this).isFile) {
            pickBackgroundPicture()
            return
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.background_picture)
            .setPositiveButton(R.string.background_choose) { _, _ -> pickBackgroundPicture() }
            .setNeutralButton(R.string.background_remove) { _, _ ->
                PictureBackground.remove(this)
                recreate()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun pickBackgroundPicture() {
        val pick = android.content.Intent(android.content.Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(android.content.Intent.CATEGORY_OPENABLE)
            type = "image/*"
        }
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_BACKGROUND)
    }

    private fun pickBackupFile() {
        val pick = android.content.Intent(android.content.Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(android.content.Intent.CATEGORY_OPENABLE)
            type = "application/json"
            putExtra(android.content.Intent.EXTRA_TITLE, "babarify-backup.json")
        }
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_BACKUP)
    }

    private fun pickRestoreFile() {
        val pick = android.content.Intent(android.content.Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(android.content.Intent.CATEGORY_OPENABLE)
            type = "*/*"
        }
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_RESTORE)
    }

    @Deprecated("The activity result API would add androidx.activity for one call.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: android.content.Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (resultCode != RESULT_OK || uri == null) return
        when (requestCode) {
            REQUEST_BACKUP -> writeBackup(uri)
            REQUEST_BACKGROUND -> try {
                PictureBackground.set(this, uri)
                recreate()
            } catch (_: java.io.IOException) {
                Toast.makeText(this, R.string.cover_not_saved, Toast.LENGTH_LONG).show()
            }
            REQUEST_RESTORE -> AlertDialog.Builder(this)
                .setTitle(R.string.backup_restore)
                .setMessage(R.string.backup_restore_question)
                .setPositiveButton(R.string.backup_restore) { _, _ -> restoreBackup(uri) }
                .setNegativeButton(android.R.string.cancel, null)
                .show()
        }
    }

    private fun writeBackup(uri: android.net.Uri) {
        val message = try {
            contentResolver.openOutputStream(uri)?.use { Backup.write(this, it) }
            R.string.backup_saved
        } catch (_: java.io.IOException) {
            R.string.backup_not_saved
        }
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun restoreBackup(uri: android.net.Uri) {
        try {
            val restored = contentResolver.openInputStream(uri)?.use { Backup.restore(this, it) } ?: return
            val text = getString(R.string.backup_restored, restored.playlists, restored.favourites)
            Toast.makeText(this, text, Toast.LENGTH_LONG).show()
            recreate()
        } catch (unusable: Backup.Unusable) {
            val reason = when (unusable.reason) {
                Backup.Reason.NOT_A_BACKUP -> R.string.backup_not_a_backup
                Backup.Reason.TOO_NEW -> R.string.backup_too_new
            }
            Toast.makeText(this, reason, Toast.LENGTH_LONG).show()
        } catch (_: java.io.IOException) {
            Toast.makeText(this, R.string.backup_not_a_backup, Toast.LENGTH_LONG).show()
        }
    }

    private fun chooseHiddenSongs() {
        val hidden = preferences.hiddenSongs
        val songs = MusicLibrary.everySong(this).filter { it.uri in hidden }
        if (songs.isEmpty()) {
            preferences.hiddenSongs = emptySet() // Any left are files that have since gone.
            Toast.makeText(this, R.string.no_hidden_songs, Toast.LENGTH_SHORT).show()
            return
        }
        val chosen = BooleanArray(songs.size)
        AlertDialog.Builder(this)
            .setTitle(R.string.hidden_songs)
            .setMultiChoiceItems(songs.map { it.title }.toTypedArray(), chosen) { _, which, ticked ->
                chosen[which] = ticked
            }
            .setPositiveButton(R.string.show_again) { _, _ ->
                val back = songs.filterIndexed { index, _ -> chosen[index] }.map { it.uri }
                preferences.hiddenSongs = preferences.hiddenSongs - back.toSet()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun clearRecent() {
        val history = HistoryStore(this)
        try {
            history.recent(Int.MAX_VALUE).forEach { releaseFileAccess(this, it.uri) }
            history.clear()
            LibraryStore(this).use { it.clearPlays() }
        } finally {
            history.close()
        }
        Toast.makeText(this, R.string.clear_recent, Toast.LENGTH_SHORT).show()
    }

    /** Nothing is sent, and there are no file names: the user copies this into a report themselves. */
    private fun showReport() {
        val version = packageManager.getPackageInfo(packageName, 0).versionName.orEmpty()
        val text = getString(
            R.string.report_text,
            version,
            Build.VERSION.RELEASE,
            Build.VERSION.SDK_INT,
            Build.MANUFACTURER,
            Build.MODEL,
            Build.SUPPORTED_ABIS.firstOrNull().orEmpty(),
            preferences.hardwareDecoding.toString(),
        )
        AlertDialog.Builder(this)
            .setTitle(R.string.report_problem)
            .setMessage(getString(R.string.report_note) + "\n\n" + text)
            .setPositiveButton(R.string.report_copy) { _, _ ->
                getSystemService(ClipboardManager::class.java)
                    .setPrimaryClip(ClipData.newPlainText(getString(R.string.report_clipboard_label), text))
                Toast.makeText(this, R.string.report_copied, Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun pick(labels: List<String>, checked: Int, onPick: (Int) -> Unit) {
        AlertDialog.Builder(this)
            .setSingleChoiceItems(labels.toTypedArray(), checked) { dialog, which ->
                onPick(which)
                dialog.dismiss()
            }
            .show()
    }

    /** Starts a titled card; the rows that follow go inside it. */
    private fun section(label: Int) {
        form.addView(
            TextView(this).apply {
                setTextAppearance(R.style.Text_Section)
                setText(label)
                setPadding(dp(4), dp(24), 0, dp(8))
            },
        )
        card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_card)
            setPadding(0, dp(4), 0, dp(4))
        }
        form.addView(card)
    }

    private fun note(label: Int) {
        card.addView(
            TextView(this).apply {
                setTextAppearance(R.style.Text_Muted)
                setText(label)
                setPadding(dp(16), dp(4), dp(16), dp(12))
            },
        )
    }

    @Suppress("DEPRECATION") // Switch is the framework's own; SwitchMaterial would bring in a whole library.
    private fun check(label: Int, value: Boolean, onChange: (Boolean) -> Unit) {
        card.addView(
            Switch(this).apply {
                setText(label)
                setTextAppearance(R.style.Text_Body)
                isChecked = value
                minHeight = dp(52)
                setPadding(dp(16), dp(8), dp(12), dp(8))
                setOnCheckedChangeListener { _, on -> onChange(on) }
            },
        )
    }

    private fun choice(label: String, onClick: () -> Unit) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dp(52)
            setPadding(dp(16), dp(8), dp(12), dp(8))
            setBackgroundResource(R.drawable.bg_row)
            isClickable = true
            isFocusable = true
            setOnClickListener { onClick() }
        }
        row.addView(
            TextView(this).apply {
                setTextAppearance(R.style.Text_Body)
                text = label
            },
            LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f),
        )
        row.addView(
            ImageView(this).apply {
                setImageResource(R.drawable.ic_chevron)
                imageTintList = android.content.res.ColorStateList.valueOf(themeColor(R.attr.inkMutedColor))
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            },
        )
        card.addView(row)
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private companion object {
        const val REQUEST_BACKUP = 21
        const val REQUEST_RESTORE = 22
        const val REQUEST_BACKGROUND = 23
    }
}
