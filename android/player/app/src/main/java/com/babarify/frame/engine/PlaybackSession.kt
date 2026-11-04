package com.babarify.frame.engine

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.OpenableColumns
import android.view.TextureView
import com.babarify.frame.core.AbLoop
import com.babarify.frame.core.ChapterInfo
import com.babarify.frame.core.ErrorCode
import com.babarify.frame.core.PlayQueue
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.core.QueueItem
import com.babarify.frame.core.RepeatMode
import com.babarify.frame.core.TrackInfo
import com.babarify.frame.core.TrackKind
import com.babarify.frame.data.HistoryEntry
import com.babarify.frame.data.HistoryStore
import com.babarify.frame.data.Preferences
import java.io.File

interface SessionListener {
    fun onPlaybackStateChanged(state: PlaybackState, error: ErrorCode?)
    fun onMediaChanged()
    fun onTracksChanged() = Unit
}

/**
 * Owns playback for the whole app, so sound can outlive the player screen: always for audio files,
 * and for video only when the user asks for that in Settings. Otherwise the screen releases the
 * engine as it leaves, and then nothing plays or reads media in the background. Main thread only.
 */
class PlaybackSession private constructor(private val app: Context) : EngineListener {
    val preferences = Preferences(app)
    private val history = HistoryStore(app)
    private val audioManager = app.getSystemService(AudioManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private val listeners = LinkedHashSet<SessionListener>()

    var engine: PlayerEngine? = null
        private set
    var mediaUri: Uri? = null
        private set
    var title = ""
        private set
    var subtitleFile: File? = null
    var queue = PlayQueue(emptyList())
        private set
    var wantsToPlay = true
    var finished = false
        private set
    var openedAt = 0L
        private set
    private var storedPositionMs = 0L
    private var lastSavedAt = 0L
    private var videoView: TextureView? = null
    private var guarding = false
    private var tracksApplied = false
    private var chosenAudio: Int? = null
    private var chosenSubtitle: Int? = null

    // Per-file settings, kept across engine restarts.
    val abLoop = AbLoop()
    var rate = 1f
        private set
    var volume = preferences.volume
        private set
    var muted = false
        private set
    var audioDelayMs = 0L
        private set
    var subtitleDelayMs = 0L
        private set
    var aspectRatio = ""
        private set
    var repeatMode = preferences.repeatMode
        private set

    val state: PlaybackState? get() = engine?.state
    val isPlaying: Boolean get() = engine?.state == PlaybackState.PLAYING
    val isAudioOnly: Boolean
        get() = engine?.let { PlaybackRules.isAudioOnly(title, it.progressed, it.hasVideoTrack) } == true
    val positionMs: Long get() = engine?.positionMs ?: storedPositionMs
    val durationMs: Long? get() = engine?.durationMs
    val volumeMaximum: Int get() = PlaybackRules.volumeMaximum(preferences.allowVolumeBoost)

    private val tick = object : Runnable {
        override fun run() {
            onTick()
            if (engine != null) handler.postDelayed(this, TICK_MS)
        }
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
                    pause()
                }
            }
            .build()
    }
    private val noisyReceiver = object : BroadcastReceiver() {
        // Headphones were unplugged: don't suddenly play out loud.
        override fun onReceive(context: Context, intent: Intent) = pause()
    }

    fun addListener(listener: SessionListener) {
        listeners += listener
    }

    fun removeListener(listener: SessionListener) {
        listeners -= listener
    }

    /** Is this file already loaded, for example playing on from the background? */
    fun isLoaded(uri: Uri): Boolean = mediaUri == uri && engine != null

    /** Chooses what plays next. The engine starts in [start]. */
    fun load(uri: Uri, displayTitle: String, newQueue: PlayQueue = PlayQueue(listOf(QueueItem(uri.toString(), displayTitle)))) {
        if (!finished) engine?.let { storedPositionMs = it.positionMs }
        saveProgress()
        releaseEngine()
        queue = newQueue
        prepare(uri, displayTitle)
    }

    private fun prepare(uri: Uri, displayTitle: String) {
        mediaUri = uri
        title = displayTitle
        subtitleFile = null
        wantsToPlay = true
        finished = false
        abLoop.clear()
        rate = 1f
        audioDelayMs = 0
        subtitleDelayMs = 0
        aspectRatio = ""
        chosenAudio = null
        chosenSubtitle = null
        val saved = history.find(uri.toString())
        storedPositionMs = if (preferences.resumePlayback && saved != null) {
            PlaybackRules.resumePosition(saved.positionMs, saved.durationMs, saved.finished)
        } else {
            0
        }
    }

    /** After Android recreated the app: put back what the screen saved. */
    fun restore(uri: Uri, displayTitle: String, subtitle: File?, position: Long, playing: Boolean, items: PlayQueue) {
        if (engine != null) return
        mediaUri = uri
        title = displayTitle
        subtitleFile = subtitle
        storedPositionMs = position
        wantsToPlay = playing
        queue = items
    }

    fun clearMedia() {
        saveProgress()
        releaseEngine()
        mediaUri = null
        title = ""
    }

    /** Throws nothing: an unreachable file arrives as an error state. */
    fun start(view: TextureView?) {
        videoView = view
        val current = engine
        if (current != null) {
            if (view == null) return
            if (!current.openedWithoutVideo || isAudioOnly) {
                current.attachVideo(view)
                return
            }
            // A video the queue moved on to in the background: open it again to show its picture.
            storedPositionMs = current.positionMs
            wantsToPlay = current.state == PlaybackState.PLAYING
            releaseEngine()
        }
        val media = mediaUri ?: return
        val created = LibVlcEngine(
            app,
            EngineOptions(preferences.hardwareDecoding, preferences.subtitleStyle),
            this,
        )
        engine = created
        if (view != null) created.attachVideo(view)
        openedAt = SystemClock.elapsedRealtime()
        finished = false
        tracksApplied = false
        try {
            created.open(media, subtitleFile, storedPositionMs, startPaused = !wantsToPlay, withVideo = view != null)
        } catch (_: MediaAccessException) {
            releaseEngine()
            notifyState(PlaybackState.ERROR, ErrorCode.MEDIA_NOT_FOUND)
            return
        }
        applyEngineSettings()
        registerGuards()
        if (wantsToPlay) audioManager.requestAudioFocus(focusRequest)
        handler.removeCallbacks(tick)
        handler.post(tick)
    }

    /** The user left the screen and sound should keep going: nothing to draw on until they return. */
    fun continueWithoutVideo() {
        videoView = null
        engine?.detachVideo()
    }

    /** The user left, or the screen closed: keep the place, free the engine. */
    fun stop() {
        engine?.let {
            // A finished file comes back at its start, ready to play again.
            storedPositionMs = if (finished) 0 else it.positionMs
            wantsToPlay = it.state == PlaybackState.PLAYING || it.state == PlaybackState.LOADING
        }
        saveProgress()
        releaseEngine()
        videoView = null
    }

    fun restartEngine() {
        val view = videoView
        stop()
        start(view)
    }

    private fun releaseEngine() {
        engine?.release()
        engine = null
        handler.removeCallbacks(tick)
        unregisterGuards()
        audioManager.abandonAudioFocusRequest(focusRequest)
    }

    @SuppressLint("UnspecifiedRegisterReceiverFlag") // A protected system broadcast.
    private fun registerGuards() {
        if (guarding) return
        guarding = true
        app.registerReceiver(noisyReceiver, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY))
    }

    private fun unregisterGuards() {
        if (!guarding) return
        guarding = false
        app.unregisterReceiver(noisyReceiver)
    }

    // ------------------------------------------------------------- events
    override fun onStateChanged(state: PlaybackState, error: ErrorCode?) {
        when (state) {
            PlaybackState.PLAYING -> applyEngineSettings()
            PlaybackState.ENDED -> {
                finished = true
                wantsToPlay = false
                storedPositionMs = 0
                saveProgress()
                val next = queue.afterEnd(repeatMode)
                if (next != null) {
                    playItem(next)
                    return
                }
            }
            else -> Unit
        }
        notifyState(state, error)
    }

    override fun onTracksChanged() {
        listeners.toList().forEach { it.onTracksChanged() }
    }

    private fun notifyState(state: PlaybackState, error: ErrorCode?) {
        listeners.toList().forEach { it.onPlaybackStateChanged(state, error) }
    }

    private fun onTick() {
        val current = engine ?: return
        val state = current.state
        val elapsed = SystemClock.elapsedRealtime() - openedAt
        if (state != PlaybackState.ERROR &&
            PlaybackRules.hasOpenTimedOut(elapsed, current.progressed, wantsToPlay && !finished)
        ) {
            current.pause()
            wantsToPlay = false
            notifyState(PlaybackState.ERROR, ErrorCode.MEDIA_OPEN_FAILED)
            return
        }
        if (current.progressed) applyTrackChoices(current)
        abLoop.jumpTarget(current.positionMs)?.let(current::seekTo)
        if (state == PlaybackState.PLAYING && SystemClock.elapsedRealtime() - lastSavedAt > SAVE_INTERVAL_MS) {
            storedPositionMs = current.positionMs
            saveProgress()
        }
    }

    /** Once per engine, after the tracks are known: what the user chose, or else their languages. */
    private fun applyTrackChoices(current: PlayerEngine) {
        if (tracksApplied) return
        tracksApplied = true
        val audio = chosenAudio ?: matchingTrack(current, TrackKind.AUDIO, preferences.preferredAudioLanguage)
        audio?.let { current.selectTrack(TrackKind.AUDIO, it) }
        val subtitles = current.tracks(TrackKind.SUBTITLE).filter { it.id != TrackInfo.DISABLED_ID }
        val subtitle = chosenSubtitle
            ?: matchingTrack(current, TrackKind.SUBTITLE, preferences.preferredSubtitleLanguage)
            ?: subtitles.firstOrNull()?.id?.takeIf { preferences.subtitlesAuto }
        subtitle?.let { current.selectTrack(TrackKind.SUBTITLE, it) }
    }

    private fun matchingTrack(current: PlayerEngine, kind: TrackKind, language: String): Int? =
        current.tracks(kind).firstOrNull { PlaybackRules.languageMatches(language, it.title) }?.id

    private fun applyEngineSettings() {
        val current = engine ?: return
        current.setRate(rate)
        current.setVolume(if (muted) 0 else volume)
        current.setAudioDelay(audioDelayMs)
        current.setSubtitleDelay(subtitleDelayMs)
        current.setAspectRatio(aspectRatio)
        current.setEqualizer(preferences.equalizer)
    }

    /** Position is saved early and often: Android can stop the app at any time. */
    private fun saveProgress() {
        val uri = mediaUri ?: return
        if (!preferences.rememberHistory) return
        val current = engine
        if (current != null && !current.progressed && !finished) return
        lastSavedAt = SystemClock.elapsedRealtime()
        history.save(HistoryEntry(uri.toString(), title, if (finished) 0 else storedPositionMs, current?.durationMs, finished))
    }

    // ----------------------------------------------------------- controls
    fun togglePlay() {
        val current = engine
        when {
            current == null || finished -> {
                releaseEngine()
                storedPositionMs = 0
                wantsToPlay = true
                finished = false
                start(videoView)
            }
            current.state == PlaybackState.PLAYING -> pause()
            else -> resume()
        }
    }

    fun pause() {
        wantsToPlay = false
        engine?.pause()
    }

    fun resume() {
        wantsToPlay = true
        audioManager.requestAudioFocus(focusRequest)
        engine?.play()
    }

    fun seekTo(position: Long) {
        val current = engine ?: return
        current.seekTo(PlaybackRules.seekTarget(position, 0, current.durationMs))
    }

    fun seekBy(deltaMs: Long) {
        val current = engine ?: return
        current.seekTo(PlaybackRules.seekTarget(current.positionMs, deltaMs, current.durationMs))
    }

    fun startOver() {
        if (engine == null) {
            storedPositionMs = 0
        } else {
            seekTo(0)
        }
    }

    /** Off, then repeat one, then repeat all. */
    fun cycleRepeat(): RepeatMode {
        repeatMode = RepeatMode.entries[(repeatMode.ordinal + 1) % RepeatMode.entries.size]
        preferences.repeatMode = repeatMode
        return repeatMode
    }

    fun next(): Boolean {
        val item = queue.nextPressed(repeatMode) ?: return false
        playItem(item)
        return true
    }

    fun previous() {
        if (PlaybackRules.previousRestartsFile(positionMs, queue.hasPrevious)) {
            startOver()
            return
        }
        queue.previous()?.let(::playItem)
    }

    private fun playItem(item: QueueItem) {
        val view = videoView
        val uri = Uri.parse(item.uri)
        val wasFinished = finished
        if (!wasFinished) {
            storedPositionMs = engine?.positionMs ?: storedPositionMs
            saveProgress()
        }
        val keptRate = rate // Moving through a playlist shouldn't change its speed.
        releaseEngine()
        prepare(uri, item.title)
        rate = keptRate
        listeners.toList().forEach { it.onMediaChanged() }
        start(view)
    }

    fun setPlaybackRate(value: Float) {
        rate = value
        engine?.setRate(value)
    }

    /** Raising the volume unmutes, as on desktop. */
    fun setVolumeLevel(level: Int) {
        volume = PlaybackRules.clampVolume(level, preferences.allowVolumeBoost)
        muted = false
        engine?.setVolume(volume)
        if (preferences.rememberVolume) preferences.volume = volume
    }

    fun toggleMute() {
        muted = !muted
        engine?.setVolume(if (muted) 0 else volume)
    }

    /** Settings changed while the player is around. */
    fun onPreferencesChanged() {
        if (volume > volumeMaximum) setVolumeLevel(volumeMaximum)
        engine?.setEqualizer(preferences.equalizer)
    }

    fun setAudioDelay(delayMs: Long) {
        audioDelayMs = PlaybackRules.clampDelay(delayMs)
        engine?.setAudioDelay(audioDelayMs)
    }

    fun setSubtitleDelay(delayMs: Long) {
        subtitleDelayMs = PlaybackRules.clampDelay(delayMs)
        engine?.setSubtitleDelay(subtitleDelayMs)
    }

    fun applyAspectRatio(ratio: String) {
        aspectRatio = ratio
        engine?.setAspectRatio(ratio)
    }

    fun selectTrack(kind: TrackKind, id: Int) {
        if (kind == TrackKind.AUDIO) chosenAudio = id else chosenSubtitle = id
        engine?.selectTrack(kind, id)
    }

    fun tracks(kind: TrackKind): List<TrackInfo> = engine?.tracks(kind).orEmpty()

    fun chapters(): List<ChapterInfo> = engine?.chapters().orEmpty()

    fun nextChapter() {
        val starts = chapters().map { it.startMs }
        starts.firstOrNull { it > positionMs }?.let(::seekTo)
    }

    fun previousChapter() {
        val starts = chapters().map { it.startMs }
        if (starts.isNotEmpty()) seekTo(starts[PlaybackRules.previousChapterIndex(starts, positionMs)])
    }

    fun displayName(uri: Uri): String? = try {
        app.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getString(0) else null
        }
    } catch (_: SecurityException) {
        null
    } catch (_: IllegalArgumentException) {
        null
    }

    companion object {
        private const val TICK_MS = 200L
        private const val SAVE_INTERVAL_MS = 5_000L

        @SuppressLint("StaticFieldLeak") // Holds only the application context.
        private var instance: PlaybackSession? = null

        fun get(context: Context): PlaybackSession =
            instance ?: PlaybackSession(context.applicationContext).also { instance = it }
    }
}
