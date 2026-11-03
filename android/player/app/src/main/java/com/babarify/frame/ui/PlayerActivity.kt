package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.OpenableColumns
import android.view.SurfaceView
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import com.babarify.frame.R
import com.babarify.frame.core.ErrorCode
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.core.TrackInfo
import com.babarify.frame.core.TrackKind
import com.babarify.frame.data.HistoryEntry
import com.babarify.frame.data.HistoryStore
import com.babarify.frame.data.Preferences
import com.babarify.frame.engine.EngineListener
import com.babarify.frame.engine.LibVlcEngine
import com.babarify.frame.engine.MediaAccessException
import com.babarify.frame.engine.PlayerEngine
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.io.InputStream

/**
 * Plays one file. The engine exists only while the screen is visible: leaving the app releases it
 * and its decoders, so nothing plays or reads media in the background.
 */
class PlayerActivity : Activity(), EngineListener {
    private lateinit var surface: SurfaceView
    private lateinit var controls: View
    private lateinit var messageLabel: TextView
    private lateinit var titleLabel: TextView
    private lateinit var seekBar: SeekBar
    private lateinit var positionLabel: TextView
    private lateinit var durationLabel: TextView
    private lateinit var playButton: Button
    private lateinit var history: HistoryStore
    private lateinit var preferences: Preferences
    private lateinit var audioManager: AudioManager

    private var engine: PlayerEngine? = null
    private var mediaUri: Uri? = null
    private var title = ""
    private var subtitleFile: File? = null
    private var positionMs = 0L
    private var wantsToPlay = true
    private var finished = false
    private var openedAt = 0L
    private var userSeeking = false
    private var lastSavedAt = 0L

    private val handler = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            onTick()
            handler.postDelayed(this, TICK_MS)
        }
    }
    private val hideControls = Runnable {
        if (engine?.state == PlaybackState.PLAYING && !userSeeking) controls.visibility = View.GONE
    }

    private val focusRequest by lazy {
        AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MOVIE)
                    .build(),
            )
            .setOnAudioFocusChangeListener { change ->
                // Another app took the sound, for example a phone call: stop rather than talk over it.
                if (change == AudioManager.AUDIOFOCUS_LOSS || change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) {
                    pausePlayback()
                }
            }
            .build()
    }
    private val noisyReceiver = object : BroadcastReceiver() {
        // Headphones were unplugged: don't suddenly play out loud.
        override fun onReceive(context: Context, intent: Intent) = pausePlayback()
    }

    /** For tests and diagnostics. */
    val playbackState: PlaybackState? get() = engine?.state
    val currentPositionMs: Long get() = engine?.positionMs ?: positionMs
    val engineInstance: Any? get() = engine
    val visibleMessage: CharSequence? get() = messageLabel.text.takeIf { messageLabel.visibility == View.VISIBLE }
    val controlsView: View get() = controls
    fun tracksOf(kind: TrackKind): List<TrackInfo> = engine?.tracks(kind).orEmpty()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_player)
        bindViews()
        history = HistoryStore(this)
        preferences = Preferences(this)
        audioManager = getSystemService(AudioManager::class.java)
        volumeControlStream = AudioManager.STREAM_MUSIC

        if (savedInstanceState != null) {
            mediaUri = savedInstanceState.getString(STATE_URI)?.let(Uri::parse)
            title = savedInstanceState.getString(STATE_TITLE).orEmpty()
            subtitleFile = savedInstanceState.getString(STATE_SUBTITLE)?.let(::File)
            positionMs = savedInstanceState.getLong(STATE_POSITION)
            wantsToPlay = savedInstanceState.getBoolean(STATE_PLAYING)
        } else {
            acceptIntent(intent)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        saveProgress()
        releaseEngine()
        subtitleFile = null
        wantsToPlay = true
        finished = false
        setIntent(intent)
        acceptIntent(intent)
        // Only needed when already visible; otherwise onStart follows and starts the engine.
        if (window.decorView.isShown) startEngine()
    }

    private fun acceptIntent(intent: Intent) {
        val uri = intent.data
        if (uri == null || !PlaybackRules.isOpenableScheme(uri.scheme)) {
            mediaUri = null
            showMessage(getString(R.string.error_media_not_found))
            return
        }
        mediaUri = uri
        title = displayName(uri) ?: getString(R.string.untitled)
        titleLabel.text = title
        val saved = history.find(uri.toString())
        positionMs = if (preferences.resumePlayback && saved != null) {
            PlaybackRules.resumePosition(saved.positionMs, saved.durationMs, saved.finished)
        } else {
            0
        }
    }

    override fun onStart() {
        super.onStart()
        registerReceiver(noisyReceiver, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY))
        handler.post(tick)
        startEngine()
    }

    override fun onStop() {
        handler.removeCallbacks(tick)
        handler.removeCallbacks(hideControls)
        unregisterReceiver(noisyReceiver)
        engine?.let {
            // A finished file comes back at its start, ready to play again.
            positionMs = if (finished) 0 else it.positionMs
            wantsToPlay = it.state == PlaybackState.PLAYING || it.state == PlaybackState.LOADING
        }
        saveProgress()
        releaseEngine()
        super.onStop()
    }

    override fun onDestroy() {
        history.close()
        super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString(STATE_URI, mediaUri?.toString())
        outState.putString(STATE_TITLE, title)
        outState.putString(STATE_SUBTITLE, subtitleFile?.path)
        outState.putLong(STATE_POSITION, engine?.positionMs ?: positionMs)
        outState.putBoolean(STATE_PLAYING, wantsToPlay)
    }

    private fun startEngine() {
        val media = mediaUri ?: return
        if (engine != null) return
        messageLabel.visibility = View.GONE
        val created = LibVlcEngine(this, preferences.hardwareDecoding, this)
        engine = created
        created.attach(surface)
        openedAt = SystemClock.elapsedRealtime()
        finished = false
        try {
            created.open(media, subtitleFile, positionMs, startPaused = !wantsToPlay)
        } catch (_: MediaAccessException) {
            releaseEngine()
            showMessage(getString(R.string.error_media_not_found))
            return
        }
        if (wantsToPlay) audioManager.requestAudioFocus(focusRequest)
        showControls()
    }

    private fun releaseEngine() {
        engine?.release()
        engine = null
        audioManager.abandonAudioFocusRequest(focusRequest)
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    override fun onStateChanged(state: PlaybackState, error: ErrorCode?) {
        val playing = state == PlaybackState.PLAYING
        playButton.setText(if (playing) R.string.pause else R.string.play)
        if (playing) messageLabel.visibility = View.GONE
        if (playing) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            scheduleHideControls()
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            showControls()
        }
        when (state) {
            PlaybackState.ENDED -> {
                finished = true
                wantsToPlay = false
                positionMs = 0
                saveProgress()
                seekBar.progress = seekBar.max
            }
            PlaybackState.ERROR -> showMessage(getString(messageFor(error)))
            else -> Unit
        }
    }

    override fun onTracksChanged() = Unit

    private fun messageFor(error: ErrorCode?): Int = when (error) {
        ErrorCode.MEDIA_NOT_FOUND -> R.string.error_media_not_found
        ErrorCode.MEDIA_OPEN_FAILED, null -> R.string.error_media_open_failed
        ErrorCode.ENGINE_FAILURE -> R.string.error_engine_failure
    }

    private fun showPreparing() {
        if (messageLabel.visibility == View.VISIBLE) return
        messageLabel.setText(R.string.preparing)
        messageLabel.visibility = View.VISIBLE
    }

    private fun showMessage(text: String) {
        messageLabel.text = text
        messageLabel.visibility = View.VISIBLE
        playButton.setText(R.string.play)
        showControls()
    }

    private fun onTick() {
        val current = engine ?: return
        val state = current.state
        if (state != PlaybackState.ERROR && PlaybackRules.hasOpenTimedOut(
                SystemClock.elapsedRealtime() - openedAt, current.progressed, wantsToPlay && !finished,
            )
        ) {
            current.pause()
            wantsToPlay = false
            showMessage(getString(R.string.error_media_open_failed))
            return
        }
        if (PlaybackRules.shouldShowPreparing(state, SystemClock.elapsedRealtime() - openedAt)) {
            showPreparing()
        }
        val duration = current.durationMs
        if (!userSeeking && !finished) {
            val position = current.positionMs
            positionLabel.text = PlaybackRules.formatTime(position)
            seekBar.progress = if (duration != null) (position * seekBar.max / duration).toInt() else 0
        }
        durationLabel.text = duration?.let(PlaybackRules::formatTime).orEmpty()
        if (state == PlaybackState.PLAYING && SystemClock.elapsedRealtime() - lastSavedAt > SAVE_INTERVAL_MS) {
            positionMs = current.positionMs
            saveProgress()
        }
    }

    /** Position is saved early and often: Android can stop the app at any time. */
    private fun saveProgress() {
        val uri = mediaUri ?: return
        val current = engine
        if (current != null && !current.progressed && !finished) return
        lastSavedAt = SystemClock.elapsedRealtime()
        history.save(
            HistoryEntry(uri.toString(), title, if (finished) 0 else positionMs, current?.durationMs, finished),
        )
    }

    private fun pausePlayback() {
        wantsToPlay = false
        engine?.pause()
    }

    private fun togglePlay() {
        val current = engine
        when {
            current == null || finished -> {
                releaseEngine()
                positionMs = 0
                wantsToPlay = true
                startEngine()
            }
            current.state == PlaybackState.PLAYING -> pausePlayback()
            else -> {
                wantsToPlay = true
                audioManager.requestAudioFocus(focusRequest)
                current.play()
            }
        }
    }

    private fun seekBy(deltaMs: Long) {
        val current = engine ?: return
        current.seekTo(PlaybackRules.seekTarget(current.positionMs, deltaMs, current.durationMs))
        showControls()
    }

    private fun showControls() {
        controls.visibility = View.VISIBLE
        scheduleHideControls()
    }

    private fun scheduleHideControls() {
        handler.removeCallbacks(hideControls)
        handler.postDelayed(hideControls, HIDE_CONTROLS_MS)
    }

    private fun showTracks(kind: TrackKind) {
        val tracks = engine?.tracks(kind).orEmpty()
        val titles = tracks.map { if (it.id == TrackInfo.DISABLED_ID) getString(R.string.track_off) else it.title }
        val builder = AlertDialog.Builder(this)
            .setTitle(if (kind == TrackKind.AUDIO) R.string.audio else R.string.subtitles)
        if (titles.isEmpty()) builder.setMessage(R.string.no_tracks)
        builder.setSingleChoiceItems(titles.toTypedArray(), tracks.indexOfFirst { it.selected }) { dialog, which ->
            selectTrack(kind, tracks[which].id)
            dialog.dismiss()
        }
        if (kind == TrackKind.SUBTITLE) builder.setNeutralButton(R.string.add_subtitle_file) { _, _ -> pickSubtitle() }
        builder.show()
    }

    private fun pickSubtitle() {
        val pick = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
        }
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_SUBTITLE)
    }

    @Deprecated("The activity result API would add androidx.activity for one call.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (requestCode != REQUEST_SUBTITLE || resultCode != RESULT_OK || uri == null) return
        // Android calls onStart before delivering this result, so the engine is already running.
        addSubtitle(uri)
    }

    fun addSubtitle(uri: Uri) {
        val file = copySubtitle(uri)
        if (file == null) {
            Toast.makeText(this, R.string.error_subtitle, Toast.LENGTH_LONG).show()
            return
        }
        subtitleFile = file
        engine?.addSubtitle(file)
    }

    fun selectTrack(kind: TrackKind, id: Int) {
        engine?.selectTrack(kind, id)
    }

    /**
     * libVLC reads subtitles by path, not through a `content:` address, so the one picked file is
     * copied into this app's private cache. Returns null if it isn't an acceptable subtitle file.
     */
    private fun copySubtitle(uri: Uri): File? {
        val extension = PlaybackRules.subtitleExtension(displayName(uri)) ?: return null
        val target = File(cacheDir, "subtitle.$extension")
        return try {
            contentResolver.openInputStream(uri)?.use { input ->
                val bytes = input.buffered().readAtMost(PlaybackRules.MAX_SUBTITLE_BYTES.toInt() + 1)
                if (bytes.size > PlaybackRules.MAX_SUBTITLE_BYTES) return null
                target.writeBytes(bytes)
            }
            target.takeIf { it.exists() }
        } catch (_: IOException) {
            null
        } catch (_: SecurityException) {
            null
        }
    }

    private fun InputStream.readAtMost(limit: Int): ByteArray {
        val bytes = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (bytes.size() < limit) {
            val count = read(buffer, 0, minOf(buffer.size, limit - bytes.size()))
            if (count < 0) break
            bytes.write(buffer, 0, count)
        }
        return bytes.toByteArray()
    }

    private fun displayName(uri: Uri): String? = try {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getString(0) else null
        }
    } catch (_: SecurityException) {
        null
    } catch (_: IllegalArgumentException) {
        null
    }

    private fun bindViews() {
        surface = findViewById(R.id.videoSurface)
        controls = findViewById(R.id.controls)
        messageLabel = findViewById(R.id.messageLabel)
        titleLabel = findViewById(R.id.titleLabel)
        seekBar = findViewById(R.id.seekBar)
        positionLabel = findViewById(R.id.positionLabel)
        durationLabel = findViewById(R.id.durationLabel)
        playButton = findViewById(R.id.playButton)
        applySystemBarPadding(controls, includeTop = false)

        surface.setOnClickListener {
            if (controls.visibility == View.VISIBLE) controls.visibility = View.GONE else showControls()
        }
        surface.addOnLayoutChangeListener { _, left, top, right, bottom, _, _, _, _ ->
            engine?.setWindowSize(right - left, bottom - top)
        }
        playButton.setOnClickListener { togglePlay() }
        findViewById<Button>(R.id.backButton).setOnClickListener { seekBy(-PlaybackRules.SEEK_STEP_MS) }
        findViewById<Button>(R.id.forwardButton).setOnClickListener { seekBy(PlaybackRules.SEEK_STEP_MS) }
        findViewById<Button>(R.id.audioButton).setOnClickListener { showTracks(TrackKind.AUDIO) }
        findViewById<Button>(R.id.subtitleButton).setOnClickListener { showTracks(TrackKind.SUBTITLE) }
        findViewById<Button>(R.id.volumeButton).setOnClickListener {
            audioManager.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_SAME, AudioManager.FLAG_SHOW_UI)
        }
        seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(bar: SeekBar, progress: Int, fromUser: Boolean) {
                val duration = engine?.durationMs
                if (fromUser && duration != null) {
                    positionLabel.text = PlaybackRules.formatTime(progress * duration / bar.max)
                }
            }

            override fun onStartTrackingTouch(bar: SeekBar) {
                userSeeking = true
            }

            override fun onStopTrackingTouch(bar: SeekBar) {
                userSeeking = false
                val current = engine ?: return
                val duration = current.durationMs ?: return
                current.seekTo(bar.progress * duration / bar.max)
                scheduleHideControls()
            }
        })
    }

    private companion object {
        const val REQUEST_SUBTITLE = 2
        const val TICK_MS = 500L
        const val SAVE_INTERVAL_MS = 5_000L
        const val HIDE_CONTROLS_MS = 4_000L
        const val STATE_URI = "uri"
        const val STATE_TITLE = "title"
        const val STATE_SUBTITLE = "subtitle"
        const val STATE_POSITION = "position"
        const val STATE_PLAYING = "playing"
    }
}
