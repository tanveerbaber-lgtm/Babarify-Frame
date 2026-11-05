package com.babarify.frame.ui

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.app.PendingIntent
import android.app.PictureInPictureParams
import android.app.RemoteAction
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Paint
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.Icon
import android.media.AudioManager
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.provider.Settings
import android.util.Rational
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.TextureView
import android.view.ViewGroup
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import com.babarify.frame.R
import com.babarify.frame.core.MusicRules
import com.babarify.frame.core.VisualStyle
import com.babarify.frame.core.ErrorCode
import com.babarify.frame.core.LeaveAction
import com.babarify.frame.core.PlayQueue
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.core.QueueItem
import com.babarify.frame.core.RepeatMode
import com.babarify.frame.core.TrackInfo
import com.babarify.frame.core.TrackKind
import com.babarify.frame.core.VideoGeometry
import com.babarify.frame.core.VideoTransform
import com.babarify.frame.data.LibraryStore
import com.babarify.frame.data.Preferences
import com.babarify.frame.engine.BackgroundPlaybackService
import com.babarify.frame.engine.PlaybackSession
import com.babarify.frame.engine.SessionListener
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.abs

/** Where a button sits while a video shows. */
private class Placed(val view: View, val parent: ViewGroup, val index: Int, val params: ViewGroup.LayoutParams)

/**
 * The player screen. What plays lives in [PlaybackSession]; leaving this screen stops it unless the
 * user chose otherwise in Settings, so by default nothing plays or reads media in the background.
 */
class PlayerActivity : Activity(), SessionListener {
    private lateinit var video: TextureView
    private lateinit var controls: View
    private lateinit var messageLabel: TextView
    private lateinit var gestureLabel: TextView
    private lateinit var titleLabel: TextView
    private lateinit var seekBar: SeekBar
    private lateinit var positionLabel: TextView
    private lateinit var durationLabel: TextView
    private lateinit var playButton: ImageButton
    private lateinit var previousButton: ImageButton
    private lateinit var nextButton: ImageButton
    private lateinit var pictureButton: ImageButton
    private lateinit var repeatButton: ImageButton
    private lateinit var unlockButton: ImageButton
    private lateinit var audioView: View
    private lateinit var audioArt: View
    private lateinit var audioCover: ImageView
    private lateinit var audioBars: EqualizerBarsView
    private lateinit var audioTitle: TextView
    private lateinit var audioArtist: TextView
    private lateinit var speedButton: Button
    private lateinit var volumeButton: Button
    private lateinit var previewImage: ImageView
    private lateinit var session: PlaybackSession
    private lateinit var preferences: Preferences
    private lateinit var library: LibraryStore
    private lateinit var worker: ExecutorService

    private var userSeeking = false
    private var transform = VideoTransform.NONE
    private var zoom = ZOOM_FIT
    private var previewRetriever: MediaMetadataRetriever? = null
    private var previewWanted: Long? = null
    private var previewRunning = false
    private var leftPicture = false
    private var coverLoadedFor: Uri? = null
    private lateinit var audioFade: View
    private lateinit var audioInfo: View
    private lateinit var bottomBar: LinearLayout
    private lateinit var toolRow: LinearLayout
    private lateinit var transportRow: LinearLayout
    private lateinit var shuffleButton: ImageButton
    private lateinit var favouriteButton: ImageButton
    private lateinit var backSeek: Button
    private lateinit var forwardSeek: Button
    private var audioLayout = false
    private var placeInVideo: List<Placed> = emptyList()
    private var locked = false

    private val handler = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            onTick()
            handler.postDelayed(this, TICK_MS)
        }
    }
    // Only a video has a picture to clear the way for. Audio's controls stay until the user hides them.
    private val hideControls = Runnable {
        if (session.isPlaying && !userSeeking && !session.isAudioOnly) setControlsVisible(false)
    }
    private val hideUnlock = Runnable { unlockButton.visibility = View.GONE }
    private val hideGestureLabel = Runnable { gestureLabel.visibility = View.GONE }

    /** For tests and diagnostics. */
    val playbackState: PlaybackState? get() = session.state
    val currentPositionMs: Long get() = session.positionMs
    val engineInstance: Any? get() = session.engine
    val visibleMessage: CharSequence? get() = messageLabel.text.takeIf { messageLabel.visibility == View.VISIBLE }
    val controlsView: View get() = controls
    val videoView: TextureView get() = video
    val currentTransform: VideoTransform get() = transform
    val isLocked: Boolean get() = locked
    fun tracksOf(kind: TrackKind): List<TrackInfo> = session.tracks(kind)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_player)
        drawBehindSystemBars()
        session = PlaybackSession.get(this)
        preferences = session.preferences
        library = LibraryStore(this)
        worker = Executors.newSingleThreadExecutor()
        bindViews()
        volumeControlStream = AudioManager.STREAM_MUSIC
        applyPicture()

        val savedUri = savedInstanceState?.getString(STATE_URI)?.let(Uri::parse)
        if (savedUri != null) {
            session.restore(
                savedUri,
                savedInstanceState.getString(STATE_TITLE).orEmpty(),
                savedInstanceState.getString(STATE_SUBTITLE)?.let(::File),
                savedInstanceState.getLong(STATE_POSITION),
                savedInstanceState.getBoolean(STATE_PLAYING),
                restoredQueue(savedInstanceState),
            )
        } else {
            acceptIntent(intent)
        }
        showMediaDetails()
    }

    private fun restoredQueue(saved: Bundle): PlayQueue {
        val uris = saved.getStringArrayList(STATE_QUEUE_URIS).orEmpty()
        val titles = saved.getStringArrayList(STATE_QUEUE_TITLES).orEmpty()
        return PlayQueue(uris.zip(titles) { uri, title -> QueueItem(uri, title) }, saved.getInt(STATE_QUEUE_INDEX))
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val loaded = intent.data?.let(session::isLoaded) == true
        acceptIntent(intent)
        if (!loaded) resetView()
        showMediaDetails()
        // Only needed when already visible; otherwise onStart follows and starts the engine.
        if (isVisible && !loaded) startPlayback()
    }

    private fun acceptIntent(intent: Intent) {
        val pending = pendingQueue
        pendingQueue = null
        val uri = intent.data
        if (uri == null || !PlaybackRules.isOpenableScheme(uri.scheme)) {
            session.clearMedia()
            showMessage(getString(R.string.error_media_not_found))
            return
        }
        if (session.isLoaded(uri)) return // Playing on from the background: just come back to it.
        val uris = intent.getStringArrayListExtra(EXTRA_QUEUE_URIS).orEmpty()
        val titles = intent.getStringArrayListExtra(EXTRA_QUEUE_TITLES).orEmpty()
        val index = intent.getIntExtra(EXTRA_QUEUE_INDEX, 0)
        val items = (pending ?: uris.zip(titles) { item, name -> QueueItem(item, name) })
            .filter { PlaybackRules.isOpenableScheme(Uri.parse(it.uri).scheme) }
        val title = items.getOrNull(index)?.takeIf { pending != null }?.title
            ?: session.displayName(uri)
            ?: getString(R.string.untitled)
        if (items.size > 1) {
            session.load(uri, title, PlayQueue(items, index))
            if (intent.getBooleanExtra(EXTRA_SHUFFLE, false)) session.toggleShuffle()
        } else {
            session.load(uri, title)
        }
    }

    override fun onStart() {
        super.onStart()
        visibleScreen = this
        closeRequested = { finish() }
        leftPicture = false
        session.addListener(this)
        handler.post(tick)
        startPlayback()
    }

    private fun startPlayback() {
        if (session.mediaUri == null) return
        messageLabel.visibility = View.GONE
        session.start(video)
        showControls()
        onTick()
        session.state?.let { onPlaybackStateChanged(it, null) }
    }

    override fun onStop() {
        handler.removeCallbacks(tick)
        handler.removeCallbacks(hideControls)
        session.removeListener(this)
        closePreview()
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        // Reopening quickly can start the next screen before this one stops: don't stop its playback.
        if (visibleScreen !== this) {
            super.onStop()
            return
        }
        visibleScreen = null
        // Audio plays on until it's closed from the notification. Video needs the user's say-so.
        val audioContinues = session.isAudioOnly && (session.isPlaying || session.state == PlaybackState.PAUSED)
        val videoContinues = !isFinishing && !leftPicture && preferences.leaveAction == LeaveAction.AUDIO &&
            session.isPlaying
        val keepSound = audioContinues || videoContinues
        if (keepSound) {
            session.continueWithoutVideo()
        } else {
            session.stop()
            if (leftPicture) session.wantsToPlay = false // Closing the small window means stop.
            BackgroundPlaybackService.stop(this)
        }
        super.onStop()
    }

    // Before the next screen starts, so its mini player knows this one is leaving. A small window stays in front.
    override fun onPause() {
        isInFront = isInPictureInPictureMode
        super.onPause()
    }

    override fun onDestroy() {
        library.close()
        worker.shutdownNow()
        super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString(STATE_URI, session.mediaUri?.toString())
        outState.putString(STATE_TITLE, session.title)
        outState.putString(STATE_SUBTITLE, session.subtitleFile?.path)
        outState.putLong(STATE_POSITION, session.positionMs)
        outState.putBoolean(STATE_PLAYING, session.wantsToPlay)
        // Saved state has a size limit that a big music collection would pass: keep what's around the current song.
        val queue = session.queue
        val first = (queue.index - SAVED_QUEUE_AROUND).coerceAtLeast(0)
        val saved = queue.items.subList(first, (queue.index + SAVED_QUEUE_AROUND + 1).coerceAtMost(queue.items.size))
        outState.putStringArrayList(STATE_QUEUE_URIS, ArrayList(saved.map { it.uri }))
        outState.putStringArrayList(STATE_QUEUE_TITLES, ArrayList(saved.map { it.title }))
        outState.putInt(STATE_QUEUE_INDEX, queue.index - first)
    }

    // ------------------------------------------------------------- events
    override fun onPlaybackStateChanged(state: PlaybackState, error: ErrorCode?) {
        val playing = state == PlaybackState.PLAYING
        showPlaying(playing)
        if (playing) {
            messageLabel.visibility = View.GONE
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            scheduleHideControls()
            startMiniPlayerIfNeeded()
            applyTransform()
            pictureButton.visibility = if (hasPicture()) View.VISIBLE else View.GONE
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            showControls()
        }
        when (state) {
            PlaybackState.ENDED -> {
                seekBar.progress = seekBar.max
                positionLabel.text = durationLabel.text
            }
            PlaybackState.ERROR -> showMessage(getString(messageFor(error)))
            else -> Unit
        }
        if (isInPictureInPictureMode) updatePictureParams()
    }

    override fun onMediaChanged() {
        resetView()
        showMediaDetails()
    }

    private fun resetView() {
        transform = VideoTransform.NONE
        zoom = ZOOM_FIT
        applyTransform()
    }

    private fun showMediaDetails() {
        titleLabel.text = session.title
        showRate(session.rate)
        showVolume()
        val inPlaylist = session.queue.isPlaylist
        previousButton.visibility = if (inPlaylist || audioLayout) View.VISIBLE else View.GONE
        nextButton.visibility = if (inPlaylist || audioLayout) View.VISIBLE else View.GONE
        showRepeat()
        showShuffle()
        showFavourite()
    }

    private fun showShuffle() {
        shuffleButton.isEnabled = session.queue.isPlaylist
        shuffleButton.alpha = if (session.queue.isPlaylist) 1f else DISABLED_ALPHA
        shuffleButton.contentDescription = getString(if (session.shuffled) R.string.shuffle_on else R.string.shuffle_off)
        shuffleButton.imageTintList = android.content.res.ColorStateList.valueOf(
            if (session.shuffled) themeColor(R.attr.accent2Color) else getColor(R.color.text),
        )
    }

    private fun showFavourite() {
        val favourite = session.mediaUri?.let { library.isFavourite(it.toString()) } == true
        favouriteButton.setImageResource(if (favourite) R.drawable.ic_heart else R.drawable.ic_heart_outline)
        favouriteButton.contentDescription = getString(if (favourite) R.string.remove_favourite else R.string.add_favourite)
        favouriteButton.imageTintList = android.content.res.ColorStateList.valueOf(
            if (favourite) FAVOURITE_COLOUR else getColor(R.color.text),
        )
    }

    /** For tests, too. */
    fun pressFavourite() {
        val uri = session.mediaUri?.toString() ?: return
        library.setFavourite(uri, session.title, !library.isFavourite(uri))
        showFavourite()
    }

    private fun pressShuffle() {
        session.toggleShuffle()
        showShuffle()
        showGesture(shuffleButton.contentDescription.toString())
    }

    private fun showQueue() {
        val queue = session.queue
        val names = queue.items.map { MusicRules.withoutExtension(it.title) }
        AlertDialog.Builder(this)
            .setTitle(R.string.queue)
            .setSingleChoiceItems(names.toTypedArray(), queue.index) { dialog, which ->
                dialog.dismiss()
                if (which != queue.index) session.playAt(which)
            }
            .show()
    }

    private fun showVisualStyles() {
        AlertDialog.Builder(this)
            .setTitle(R.string.animation_style)
            .setSingleChoiceItems(
                VISUAL_STYLES.map { getString(it.second) }.toTypedArray(),
                VISUAL_STYLES.indexOfFirst { it.first == preferences.visualStyle },
            ) { dialog, which ->
                chooseVisualStyle(VISUAL_STYLES[which].first)
                dialog.dismiss()
            }
            .show()
    }

    /** For tests, too. */
    fun chooseVisualStyle(style: VisualStyle) {
        preferences.visualStyle = style
        audioBars.style = style
    }

    private fun showEqualizer() {
        EqualizerPanel.show(this, preferences, session.engine) { session.onPreferencesChanged() }
    }

    private fun showVolume() {
        volumeButton.text = if (session.muted) "" else session.volume.toString()
        volumeButton.contentDescription =
            if (session.muted) getString(R.string.muted) else getString(R.string.volume_description, session.volume)
        volumeButton.setCompoundDrawablesRelativeWithIntrinsicBounds(
            if (session.muted) R.drawable.ic_muted else R.drawable.ic_volume,
            0,
            0,
            0,
        )
        centreVolumeContent()
    }

    /** A button draws its icon at the edge and its text in the middle: bring them together. */
    private fun centreVolumeContent() {
        val icon = volumeButton.compoundDrawablesRelative[0]?.intrinsicWidth ?: 0
        val text = volumeButton.paint.measureText(volumeButton.text.toString()).toInt()
        val side = ((volumeButton.width - icon - volumeButton.compoundDrawablePadding - text) / 2).coerceAtLeast(0)
        volumeButton.setPaddingRelative(side, 0, side, 0)
    }

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
        showPlaying(false)
        showControls()
    }

    /** Audio's own screen, in place of a video that would only be black. */
    private fun showAudioView() {
        val audio = session.isAudioOnly
        val wasShown = audioView.visibility == View.VISIBLE
        audioView.visibility = if (audio) View.VISIBLE else View.GONE
        if (audio != audioLayout) arrangeControls(audio)
        if (!audio) return
        if (!wasShown) {
            pictureButton.visibility = View.GONE
            showControls() // The queue may have moved here from a video with its controls hidden.
            placeAudioCover()
        }
        val uri = session.mediaUri ?: return
        if (coverLoadedFor == uri) return
        coverLoadedFor = uri
        audioTitle.text = MusicRules.withoutExtension(session.title)
        audioArtist.text = ""
        showCover(null)
        worker.execute {
            val retriever = MediaMetadataRetriever()
            var cover: Bitmap? = null
            var title: String? = null
            var artist: String? = null
            try {
                retriever.setDataSource(this, uri)
                cover = retriever.embeddedPicture?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
                title = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)
                artist = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)
            } catch (_: RuntimeException) {
                // No details for this file: its name is enough.
            } finally {
                try {
                    retriever.release()
                } catch (_: IOException) {
                    // Nothing more to do with it.
                }
            }
            runOnUiThread {
                if (!isDestroyed && coverLoadedFor == uri) {
                    showCover(cover)
                    title?.takeIf { it.isNotBlank() }?.let { audioTitle.text = it }
                    audioArtist.text = artist.orEmpty()
                }
            }
        }
    }

    /** The song's picture and the colours taken from it, or moving bars and the theme's colours. */
    private fun showCover(cover: Bitmap?) {
        audioCover.setImageBitmap(cover)
        audioCover.visibility = if (cover != null) View.VISIBLE else View.GONE
        audioBars.visibility = if (cover != null) View.GONE else View.VISIBLE
        audioFade.visibility = if (cover != null) View.VISIBLE else View.GONE
        if (cover == null) {
            audioView.setBackgroundResource(R.drawable.bg_audio)
            return
        }
        val colour = Art.backgroundFrom(cover)
        audioView.setBackgroundColor(colour)
        audioFade.background = GradientDrawable(
            GradientDrawable.Orientation.TOP_BOTTOM,
            intArrayOf(colour and TRANSPARENT_MASK, colour),
        )
    }

    /** The picture fills what the controls leave free, and steps aside when a turned phone has too little. */
    private fun placeAudioCover() {
        if (!audioLayout) return
        val free = bottomBar.top
        if (free <= 0) return
        val density = resources.displayMetrics.density
        val height = free // Tall on a phone, like the reference: it crops the sides rather than leave a gap.
        audioArt.visibility = if (height < MIN_COVER_DP * density) View.GONE else View.VISIBLE
        val params = audioArt.layoutParams
        if (params.height != height) {
            params.height = height
            audioArt.layoutParams = params
        }
    }

    /** One set of buttons, placed for a song or for a video, so everything behaves the same in both. */
    private fun arrangeControls(audio: Boolean) {
        audioLayout = audio
        val density = resources.displayMetrics.density
        fun small() = LinearLayout.LayoutParams((ICON_DP * density).toInt(), (ICON_DP * density).toInt())
        if (audio) {
            place(transportRow, bottomBar, bottomBar.indexOfChild(toolRow), LinearLayout.LayoutParams(MATCH, WRAP))
            place(repeatButton, transportRow, transportRow.childCount, small().apply { marginStart = (6 * density).toInt() })
            place(backSeek, toolRow, 0, small())
            place(forwardSeek, toolRow, toolRow.indexOfChild(findViewById(R.id.rotateButton)), small())
        } else {
            placeInVideo.forEach { place(it.view, it.parent, it.index, it.params) }
        }
        val onlyVideo = if (audio) View.GONE else View.VISIBLE
        listOf(R.id.fitButton, R.id.audioButton, R.id.subtitleButton).forEach { findViewById<View>(it).visibility = onlyVideo }
        shuffleButton.visibility = if (audio) View.VISIBLE else View.GONE
        audioInfo.visibility = if (audio) View.VISIBLE else View.GONE
        titleLabel.visibility = if (audio) View.INVISIBLE else View.VISIBLE
        if (audio) bottomBar.background = null else bottomBar.setBackgroundResource(R.drawable.scrim_bottom)
        showMediaDetails()
        bottomBar.post { placeAudioCover() }
    }

    private fun place(view: View, parent: ViewGroup, index: Int, params: ViewGroup.LayoutParams) {
        (view.parent as? ViewGroup)?.removeView(view)
        parent.addView(view, index.coerceAtMost(parent.childCount), params)
    }

    private fun showPlaying(playing: Boolean) {
        audioBars.playing = playing
        playButton.setImageResource(if (playing) R.drawable.ic_pause else R.drawable.ic_play)
        playButton.contentDescription = getString(if (playing) R.string.pause else R.string.play)
    }

    /** Started while this screen is visible, as Android 12+ requires. */
    private fun startMiniPlayerIfNeeded() {
        if (BackgroundPlaybackService.running || !session.isPlaying) return
        if (session.isAudioOnly || preferences.leaveAction == LeaveAction.AUDIO) {
            BackgroundPlaybackService.start(this)
        }
    }

    private fun showRepeat() {
        val (icon, label) = when (session.repeatMode) {
            RepeatMode.OFF -> R.drawable.ic_repeat to R.string.repeat_off_label
            RepeatMode.ONE -> R.drawable.ic_repeat_one to R.string.repeat_one_label
            RepeatMode.ALL -> R.drawable.ic_repeat to R.string.repeat_all_label
        }
        repeatButton.setImageResource(icon)
        repeatButton.contentDescription = getString(label)
        repeatButton.imageTintList = android.content.res.ColorStateList.valueOf(
            if (session.repeatMode == RepeatMode.OFF) getColor(R.color.text) else themeColor(R.attr.accent2Color),
        )
        nextButton.isEnabled = session.queue.hasNext || session.repeatMode == RepeatMode.ALL
        nextButton.alpha = if (nextButton.isEnabled) 1f else DISABLED_ALPHA
    }

    fun pressRepeat() {
        session.cycleRepeat()
        showRepeat()
        showGesture(repeatButton.contentDescription.toString())
        showControls()
    }

    private fun onTick() {
        startMiniPlayerIfNeeded()
        showAudioView()
        // Android can deliver lifecycle calls around entering the small window in either order.
        if (isInPictureInPictureMode && controls.visibility == View.VISIBLE) setControlsVisible(false)
        val state = session.state ?: return
        if (PlaybackRules.shouldShowPreparing(state, android.os.SystemClock.elapsedRealtime() - session.openedAt)) {
            showPreparing()
        }
        val duration = session.durationMs
        if (!userSeeking && !session.finished) {
            val position = session.positionMs
            positionLabel.text = PlaybackRules.formatTime(position)
            seekBar.progress = if (duration != null) (position * seekBar.max / duration).toInt() else 0
        }
        durationLabel.text = duration?.let(PlaybackRules::formatTime).orEmpty()
    }

    // ----------------------------------------------------------- controls
    private fun seekBy(deltaMs: Long) {
        session.seekBy(deltaMs)
        showControls()
    }

    fun showControls() {
        if (isInPictureInPictureMode || locked) return
        setControlsVisible(true)
        scheduleHideControls()
    }

    /** Like other players, the screen is all video until it's touched. */
    private fun setControlsVisible(visible: Boolean) {
        if (visible && controls.visibility != View.VISIBLE) {
            controls.alpha = 0f
            controls.animate().alpha(1f).setDuration(FADE_MS).start()
        }
        controls.visibility = if (visible) View.VISIBLE else View.GONE
        setSystemBarsVisible(visible)
    }

    private fun drawBehindSystemBars() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false)
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = LAYOUT_BEHIND_BARS
        }
    }

    private fun setSystemBarsVisible(visible: Boolean) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bars = window.insetsController ?: return
            bars.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            if (visible) bars.show(WindowInsets.Type.systemBars()) else bars.hide(WindowInsets.Type.systemBars())
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = if (visible) LAYOUT_BEHIND_BARS else LAYOUT_BEHIND_BARS or HIDE_BARS
        }
    }

    private fun scheduleHideControls() {
        handler.removeCallbacks(hideControls)
        handler.postDelayed(hideControls, HIDE_CONTROLS_MS)
    }

    private fun showTracks(kind: TrackKind) {
        val tracks = session.tracks(kind)
        val titles = tracks.map { if (it.id == TrackInfo.DISABLED_ID) getString(R.string.track_off) else it.title }
        val builder = AlertDialog.Builder(this)
            .setTitle(if (kind == TrackKind.AUDIO) R.string.audio else R.string.subtitles)
        if (titles.isEmpty()) builder.setMessage(R.string.no_tracks)
        builder.setSingleChoiceItems(titles.toTypedArray(), tracks.indexOfFirst { it.selected }) { dialog, which ->
            selectTrack(kind, tracks[which].id)
            dialog.dismiss()
        }
        if (kind == TrackKind.SUBTITLE) {
            builder.setNeutralButton(R.string.add_subtitle_file) { _, _ -> pickSubtitle() }
            builder.setPositiveButton(R.string.subtitle_look) { _, _ -> showSubtitleLook() }
        }
        builder.show()
    }

    private fun showSubtitleLook() {
        SubtitleLookDialog.show(this, preferences) { session.restartEngine() }
    }

    private fun showSpeed() {
        val rates = PlaybackRules.SPEEDS
        AlertDialog.Builder(this)
            .setTitle(R.string.speed)
            .setSingleChoiceItems(rates.map(::rateLabel).toTypedArray(), rates.indexOf(session.rate)) { dialog, which ->
                setRate(rates[which])
                dialog.dismiss()
            }
            .show()
    }

    fun setRate(rate: Float) {
        session.setPlaybackRate(rate)
        showRate(rate)
    }

    private fun showRate(rate: Float) {
        speedButton.text = rateLabel(rate)
        speedButton.contentDescription = getString(R.string.speed_description, rateLabel(rate))
    }

    private fun rateLabel(rate: Float): String = getString(R.string.speed_level, rate.toString().removeSuffix(".0"))

    private fun showVolumeDialog() {
        val view = layoutInflater.inflate(R.layout.dialog_volume, null)
        val number = view.findViewById<TextView>(R.id.volumeNumber)
        val slider = view.findViewById<SeekBar>(R.id.volumeSlider)
        val hint = view.findViewById<TextView>(R.id.volumeHint)
        val mute = view.findViewById<Button>(R.id.muteButton)
        slider.max = session.volumeMaximum - PlaybackRules.VOLUME_MIN
        slider.progress = session.volume - PlaybackRules.VOLUME_MIN
        fun show() {
            number.text = session.volume.toString()
            number.setTextColor(getColor(if (session.volume > PlaybackRules.VOLUME_NORMAL_MAX) R.color.warning else R.color.text))
            hint.setText(if (preferences.allowVolumeBoost) R.string.boost_warning else R.string.boost_hint)
            mute.setText(if (session.muted) R.string.unmute else R.string.mute)
            showVolume()
        }
        slider.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(bar: SeekBar, progress: Int, fromUser: Boolean) {
                if (fromUser) {
                    session.setVolumeLevel(progress + PlaybackRules.VOLUME_MIN)
                    show()
                }
            }

            override fun onStartTrackingTouch(bar: SeekBar) = Unit
            override fun onStopTrackingTouch(bar: SeekBar) = Unit
        })
        mute.setOnClickListener {
            session.toggleMute()
            show()
        }
        show()
        AlertDialog.Builder(this).setTitle(R.string.volume).setView(view)
            .setPositiveButton(android.R.string.ok, null).show()
    }

    private fun showMore() {
        val audio = session.isAudioOnly
        val items = buildList<Pair<Int, () -> Unit>> {
            if (audio) {
                add(R.string.equalizer to { showEqualizer() })
                add(R.string.animation_style to { showVisualStyles() })
                add(R.string.audio to { showTracks(TrackKind.AUDIO) })
                add(R.string.subtitles to { showTracks(TrackKind.SUBTITLE) })
            } else {
                add(R.string.picture_and_sound to { showPictureAndSound() })
                add(R.string.aspect_ratio to { showAspect() })
                add(R.string.zoom to { showZoom() })
                add(R.string.rotate_or_flip to { showTransform() })
            }
            add(R.string.sleep_timer to { showSleepTimer() })
            add(R.string.add_to_playlist to { choosePlaylist() })
            add(R.string.lock_controls to { setLocked(true) })
            if (session.chapters().isNotEmpty()) add(R.string.chapters to { showChapters() })
            add(R.string.bookmarks to { showBookmarks() })
            add(R.string.ab_repeat to { pressAbRepeat() })
            add(R.string.sync_and_delay to { showSync() })
            add(R.string.start_over to { session.startOver() })
            if (!audio) add(R.string.take_snapshot to { takeSnapshot() })
            add(R.string.media_info to { showMediaInfo() })
            add(R.string.playback_info to { showPlaybackInfo() })
        }
        AlertDialog.Builder(this)
            .setItems(items.map { getString(it.first) }.toTypedArray()) { _, which -> items[which].second() }
            .show()
    }

    private fun showSleepTimer() {
        val minutes = SLEEP_MINUTES
        val labels = listOf(getString(R.string.sleep_off)) + minutes.map { getString(R.string.sleep_minutes, it) }
        val builder = AlertDialog.Builder(this)
        val remaining = session.sleepAt?.let { it - android.os.SystemClock.elapsedRealtime() }
        builder.setTitle(
            if (remaining == null) {
                getString(R.string.sleep_timer)
            } else {
                getString(R.string.sleep_remaining, PlaybackRules.formatTime(remaining))
            },
        )
        builder.setItems(labels.toTypedArray()) { _, which ->
            val chosen = minutes.getOrNull(which - 1)
            session.setSleepTimer(chosen?.let { it * MS_PER_MINUTE })
            val message = if (chosen == null) getString(R.string.sleep_off) else getString(R.string.sleep_set, chosen)
            Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        }
        builder.show()
    }

    private fun choosePlaylist() {
        val uri = session.mediaUri?.toString() ?: return
        val title = session.title
        val playlists = library.playlists()
        val labels = playlists.map { it.name } + getString(R.string.new_playlist)
        AlertDialog.Builder(this)
            .setTitle(R.string.add_to_playlist)
            .setItems(labels.toTypedArray()) { _, which ->
                val playlist = playlists.getOrNull(which)
                if (playlist != null) {
                    addToPlaylist(playlist.id, playlist.name, uri, title)
                } else {
                    askPlaylistName(this, null) { name -> addToPlaylist(library.createPlaylist(name), name, uri, title) }
                }
            }
            .show()
    }

    private fun addToPlaylist(id: Long, name: String, uri: String, title: String) {
        library.addToPlaylist(id, uri, title)
        Toast.makeText(this, getString(R.string.added_to_playlist, name), Toast.LENGTH_SHORT).show()
    }

    /** Locked, only the unlock button works: for a video in a pocket, or in a child's hands. */
    fun setLocked(value: Boolean) {
        locked = value
        handler.removeCallbacks(hideUnlock)
        unlockButton.visibility = View.GONE
        if (value) {
            handler.removeCallbacks(hideControls)
            setControlsVisible(false)
            showGesture(getString(R.string.controls_locked))
        } else {
            showControls()
        }
    }

    private fun offerUnlock() {
        unlockButton.visibility = View.VISIBLE
        handler.removeCallbacks(hideUnlock)
        handler.postDelayed(hideUnlock, UNLOCK_VISIBLE_MS)
    }

    private fun showPictureAndSound() {
        val engine = session.engine
        PictureSoundDialog.show(
            this,
            preferences,
            engine,
            onPicture = { applyPicture() },
            onEqualizer = { session.onPreferencesChanged() },
        )
    }

    fun applyPicture() {
        val picture = preferences.picture
        val paint = if (picture.isDefault) {
            null
        } else {
            Paint().apply { colorFilter = ColorMatrixColorFilter(ColorMatrix(picture.colorMatrix())) }
        }
        video.setLayerPaint(paint)
    }

    private fun showAspect() {
        val ratios = PlaybackRules.ASPECT_RATIOS
        val labels = ratios.map { it.ifEmpty { getString(R.string.aspect_from_file) } }
        AlertDialog.Builder(this)
            .setTitle(R.string.aspect_ratio)
            .setSingleChoiceItems(labels.toTypedArray(), ratios.indexOf(session.aspectRatio)) { dialog, which ->
                session.applyAspectRatio(ratios[which])
                dialog.dismiss()
            }
            .show()
    }

    private fun showZoom() {
        val levels = listOf(ZOOM_FIT, ZOOM_FILL, 1.25f, 1.5f, 2f)
        val labels = listOf(
            getString(R.string.zoom_fit),
            getString(R.string.zoom_fill),
            "125 %",
            "150 %",
            "200 %",
        )
        AlertDialog.Builder(this)
            .setTitle(R.string.zoom)
            .setSingleChoiceItems(labels.toTypedArray(), levels.indexOf(zoom)) { dialog, which ->
                zoom = levels[which]
                applyTransform()
                dialog.dismiss()
            }
            .show()
    }

    private fun toggleFill() {
        zoom = if (zoom == ZOOM_FIT) ZOOM_FILL else ZOOM_FIT
        applyTransform()
        showGesture(getString(if (zoom == ZOOM_FIT) R.string.fit_screen_off else R.string.fit_screen_on))
        showControls()
    }

    private fun toggleOrientation() {
        val landscape = resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
        requestedOrientation = if (landscape) {
            ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
        } else {
            ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        }
        showControls()
    }

    private fun showTransform() {
        val choices = VideoTransform.entries
        val labels = listOf(
            R.string.transform_none,
            R.string.transform_90,
            R.string.transform_180,
            R.string.transform_270,
            R.string.transform_flip_h,
            R.string.transform_flip_v,
        ).map(::getString)
        AlertDialog.Builder(this)
            .setTitle(R.string.rotate_or_flip)
            .setSingleChoiceItems(labels.toTypedArray(), choices.indexOf(transform)) { dialog, which ->
                setTransform(choices[which])
                dialog.dismiss()
            }
            .show()
    }

    fun setTransform(value: VideoTransform) {
        transform = value
        applyTransform()
    }

    private fun applyTransform() {
        val factor = if (zoom == ZOOM_FILL) {
            val size = session.engine?.videoSize
            if (size == null) 1f else VideoGeometry.fillZoom(video.width, video.height, size.first, size.second)
        } else {
            zoom
        }
        val result = VideoGeometry.viewTransform(transform, factor, video.width, video.height)
        video.rotation = result.rotation
        video.scaleX = result.scaleX
        video.scaleY = result.scaleY
    }

    private fun showChapters() {
        val chapters = session.chapters()
        val labels = chapters.map { "${PlaybackRules.formatTime(it.startMs)}  ${it.title}" }
        val current = PlaybackRules.chapterIndexAt(chapters.map { it.startMs }, session.positionMs)
        AlertDialog.Builder(this)
            .setTitle(R.string.chapters)
            .setSingleChoiceItems(labels.toTypedArray(), current) { dialog, which ->
                session.seekTo(chapters[which].startMs)
                dialog.dismiss()
            }
            .setNegativeButton(R.string.previous_chapter) { _, _ -> session.previousChapter() }
            .setPositiveButton(R.string.next_chapter) { _, _ -> session.nextChapter() }
            .show()
    }

    private fun showBookmarks() {
        val uri = session.mediaUri?.toString() ?: return
        val bookmarks = library.bookmarks(uri)
        val builder = AlertDialog.Builder(this)
            .setTitle(R.string.bookmarks)
            .setPositiveButton(R.string.add_bookmark) { _, _ -> askBookmarkLabel(uri) }
        if (bookmarks.isEmpty()) {
            builder.setMessage(R.string.no_bookmarks)
            builder.show()
            return
        }
        builder.setItems(
            bookmarks.map { "${PlaybackRules.formatTime(it.positionMs)}  ${it.label}" }.toTypedArray(),
        ) { _, which -> session.seekTo(bookmarks[which].positionMs) }
        val dialog = builder.show()
        dialog.listView.setOnItemLongClickListener { _, _, which, _ ->
            library.removeBookmark(bookmarks[which].id)
            dialog.dismiss()
            Toast.makeText(this, R.string.bookmark_removed, Toast.LENGTH_SHORT).show()
            true
        }
    }

    private fun askBookmarkLabel(uri: String) {
        val position = session.positionMs
        val input = EditText(this).apply {
            setText(PlaybackRules.formatTime(position))
            setSelectAllOnFocus(true)
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.add_bookmark)
            .setView(input)
            .setPositiveButton(android.R.string.ok) { _, _ -> addBookmark(uri, position, input.text.toString()) }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    fun addBookmark(uri: String, position: Long, label: String) {
        library.addBookmark(uri, position, label.trim().ifEmpty { PlaybackRules.formatTime(position) })
    }

    fun pressAbRepeat() {
        session.abLoop.press(session.positionMs)
        val loop = session.abLoop
        val a = loop.a
        val b = loop.b
        val message = when {
            a == null -> getString(R.string.repeat_off)
            b == null -> getString(R.string.repeat_a_set, PlaybackRules.formatTime(a))
            else -> getString(R.string.repeat_on, PlaybackRules.formatTime(a), PlaybackRules.formatTime(b))
        }
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun showSync() {
        val view = layoutInflater.inflate(R.layout.dialog_sync, null)
        val subtitle = view.findViewById<TextView>(R.id.subtitleDelayLabel)
        val audio = view.findViewById<TextView>(R.id.audioDelayLabel)
        fun show() {
            subtitle.text = getString(R.string.delay_ms, session.subtitleDelayMs)
            audio.text = getString(R.string.delay_ms, session.audioDelayMs)
        }
        val step = PlaybackRules.DELAY_STEP_MS
        view.findViewById<Button>(R.id.subtitleEarlier).setOnClickListener {
            session.setSubtitleDelay(session.subtitleDelayMs - step)
            show()
        }
        view.findViewById<Button>(R.id.subtitleLater).setOnClickListener {
            session.setSubtitleDelay(session.subtitleDelayMs + step)
            show()
        }
        view.findViewById<Button>(R.id.audioEarlier).setOnClickListener {
            session.setAudioDelay(session.audioDelayMs - step)
            show()
        }
        view.findViewById<Button>(R.id.audioLater).setOnClickListener {
            session.setAudioDelay(session.audioDelayMs + step)
            show()
        }
        show()
        AlertDialog.Builder(this)
            .setTitle(R.string.sync_and_delay)
            .setView(view)
            .setNeutralButton(R.string.reset) { _, _ ->
                session.setSubtitleDelay(0)
                session.setAudioDelay(0)
            }
            .setPositiveButton(android.R.string.ok, null)
            .show()
    }

    /** A picture of what's on screen, saved to Pictures/Babarify Frame. No permission is needed for this. */
    fun takeSnapshot() {
        val bitmap = video.bitmap
        if (bitmap == null || session.engine?.videoSize == null) {
            Toast.makeText(this, R.string.snapshot_no_video, Toast.LENGTH_LONG).show()
            return
        }
        val name = "${session.title.substringBeforeLast('.').take(60)} ${PlaybackRules.formatTime(session.positionMs).replace(':', '-')}.png"
        worker.execute {
            val saved = saveSnapshot(bitmap, name)
            runOnUiThread {
                val message = if (saved != null) R.string.snapshot_saved else R.string.snapshot_failed
                if (!isDestroyed) Toast.makeText(this, message, Toast.LENGTH_LONG).show()
                lastSnapshot = saved
            }
        }
    }

    /** For tests. */
    var lastSnapshot: Uri? = null
        private set

    private fun saveSnapshot(bitmap: Bitmap, name: String): Uri? {
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name)
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/Babarify Frame")
            put(MediaStore.Images.Media.IS_PENDING, 1)
        }
        val uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return null
        return try {
            contentResolver.openOutputStream(uri)?.use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            contentResolver.update(uri, ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }, null, null)
            uri
        } catch (_: IOException) {
            contentResolver.delete(uri, null, null)
            null
        } finally {
            bitmap.recycle()
        }
    }

    private fun showMediaInfo() {
        val uri = session.mediaUri ?: return
        val tracks = session.tracks(TrackKind.AUDIO).filter { it.id != TrackInfo.DISABLED_ID }.map { it.title }
        val subtitles = session.tracks(TrackKind.SUBTITLE).filter { it.id != TrackInfo.DISABLED_ID }.map { it.title }
        val chapters = session.chapters().size
        val size = session.engine?.videoSize
        val duration = session.durationMs
        val name = session.title
        worker.execute {
            val tags = readTags(uri)
            val text = buildString {
                appendLine(name)
                appendLine()
                duration?.let { appendLine(getString(R.string.info_duration, PlaybackRules.formatTime(it))) }
                size?.let { appendLine(getString(R.string.info_video_size, it.first, it.second)) }
                tags.forEach { appendLine(it) }
                appendLine(getString(R.string.info_audio_tracks, tracks.size))
                tracks.forEach { appendLine("  $it") }
                appendLine(getString(R.string.info_subtitle_tracks, subtitles.size))
                subtitles.forEach { appendLine("  $it") }
                appendLine(getString(R.string.info_chapters, chapters))
            }
            runOnUiThread {
                if (!isDestroyed) {
                    AlertDialog.Builder(this).setTitle(R.string.media_info).setMessage(text)
                        .setPositiveButton(android.R.string.ok, null).show()
                }
            }
        }
    }

    private fun readTags(uri: Uri): List<String> {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(this, uri)
            val labels = listOf(
                MediaMetadataRetriever.METADATA_KEY_TITLE to R.string.info_title,
                MediaMetadataRetriever.METADATA_KEY_ARTIST to R.string.info_artist,
                MediaMetadataRetriever.METADATA_KEY_ALBUM to R.string.info_album,
                MediaMetadataRetriever.METADATA_KEY_MIMETYPE to R.string.info_format,
                MediaMetadataRetriever.METADATA_KEY_BITRATE to R.string.info_bitrate,
            )
            labels.mapNotNull { (key, label) -> retriever.extractMetadata(key)?.let { getString(label, it) } }
        } catch (_: RuntimeException) {
            emptyList()
        } finally {
            try {
                retriever.release()
            } catch (_: IOException) {
                // Nothing more to do with it.
            }
        }
    }

    private fun showPlaybackInfo() {
        val stats = session.engine?.stats()
        val text = buildString {
            appendLine(getString(R.string.info_engine))
            appendLine(getString(if (preferences.hardwareDecoding) R.string.info_decoding_hw else R.string.info_decoding_sw))
            appendLine(getString(R.string.info_state, session.state?.name.orEmpty()))
            appendLine(getString(R.string.info_speed, session.rate.toString()))
            if (stats != null) {
                appendLine(getString(R.string.info_video_frames, stats.decodedVideo, stats.lostPictures))
                appendLine(getString(R.string.info_audio_blocks, stats.decodedAudio, stats.lostAudio))
            }
        }
        AlertDialog.Builder(this).setTitle(R.string.playback_info).setMessage(text)
            .setPositiveButton(android.R.string.ok, null).show()
    }

    // -------------------------------------------------- picture in picture
    private fun hasPicture(): Boolean =
        packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE) && session.engine?.videoSize != null &&
            !session.isAudioOnly

    fun enterPicture(): Boolean {
        if (!hasPicture()) return false
        return enterPictureInPictureMode(pictureParams())
    }

    private fun pictureParams(): PictureInPictureParams {
        val builder = PictureInPictureParams.Builder()
        session.engine?.videoSize?.let { (width, height) ->
            // Android refuses shapes more extreme than about 2.39:1.
            val ratio = (width.toFloat() / height).coerceIn(0.42f, 2.38f)
            builder.setAspectRatio(Rational((ratio * 1000).toInt(), 1000))
        }
        val playing = session.isPlaying
        val toggle = PendingIntent.getBroadcast(
            this,
            0,
            Intent(this, PictureToggleReceiver::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val label = getString(if (playing) R.string.pause else R.string.play)
        val icon = Icon.createWithResource(
            this,
            if (playing) android.R.drawable.ic_media_pause else android.R.drawable.ic_media_play,
        )
        builder.setActions(listOf(RemoteAction(icon, label, label, toggle)))
        return builder.build()
    }

    private fun updatePictureParams() {
        setPictureInPictureParams(pictureParams())
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        if (preferences.leaveAction == LeaveAction.PICTURE && session.isPlaying) enterPicture()
    }

    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean, newConfig: Configuration) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        if (isInPictureInPictureMode) {
            setControlsVisible(false)
        } else {
            // Either back to full screen (onResume follows) or the small window was closed (onStop follows).
            leftPicture = true
        }
    }

    override fun onResume() {
        super.onResume()
        leftPicture = false
        isInFront = true
    }

    // ----------------------------------------------------------- subtitles
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
        session.subtitleFile = file
        session.engine?.addSubtitle(file)
    }

    fun selectTrack(kind: TrackKind, id: Int) {
        session.selectTrack(kind, id)
    }

    /**
     * libVLC reads subtitles by path, not through a `content:` address, so the one picked file is
     * copied into this app's private cache. Returns null if it isn't an acceptable subtitle file.
     */
    private fun copySubtitle(uri: Uri): File? {
        val extension = PlaybackRules.subtitleExtension(session.displayName(uri)) ?: return null
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

    // ------------------------------------------------------- seek pictures
    /** Only one picture is made at a time; while dragging, the newest wish replaces any waiting one. */
    private fun requestPreview(positionMs: Long) {
        val uri = session.mediaUri ?: return
        if (!preferences.seekPreviews || session.engine?.videoSize == null) return
        previewWanted = positionMs
        if (previewRunning) return
        previewRunning = true
        worker.execute {
            try {
                val retriever = previewRetriever ?: MediaMetadataRetriever().also {
                    it.setDataSource(this, uri)
                    previewRetriever = it
                }
                while (true) {
                    val wanted = previewWanted ?: break
                    previewWanted = null
                    val frame = retriever.getScaledFrameAtTime(
                        wanted * 1000,
                        MediaMetadataRetriever.OPTION_CLOSEST_SYNC,
                        PREVIEW_WIDTH,
                        PREVIEW_HEIGHT,
                    )
                    runOnUiThread {
                        if (userSeeking && frame != null) {
                            previewImage.setImageBitmap(frame)
                            previewImage.visibility = View.VISIBLE
                        }
                    }
                }
            } catch (_: RuntimeException) {
                // No picture for this file: seeking still works.
            } finally {
                previewRunning = false
            }
        }
    }

    private fun closePreview() {
        previewImage.visibility = View.GONE
        previewImage.setImageDrawable(null)
        previewWanted = null
        val retriever = previewRetriever
        previewRetriever = null
        if (retriever != null) {
            worker.execute {
                try {
                    retriever.release()
                } catch (_: IOException) {
                    // Nothing more to do with it.
                }
            }
        }
    }

    // ------------------------------------------------------------ gestures
    private inner class Gestures(private val area: View) : GestureDetector.SimpleOnGestureListener() {
        private var mode = 0
        private var startPosition = 0L
        private var startVolume = 0
        private var startBrightness = 0f

        override fun onDown(e: MotionEvent): Boolean {
            mode = MODE_NONE
            return true
        }

        override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
            if (locked) {
                offerUnlock()
                return true
            }
            if (controls.visibility == View.VISIBLE) setControlsVisible(false) else showControls()
            return true
        }

        override fun onDoubleTap(e: MotionEvent): Boolean {
            if (!preferences.gestures || locked) return false
            val third = area.width / 3
            val step = preferences.seekStepSeconds * 1000L
            when {
                e.x < third -> {
                    session.seekBy(-step)
                    showGesture(getString(R.string.seek_by, "−${preferences.seekStepSeconds}"))
                }
                e.x > third * 2 -> {
                    session.seekBy(step)
                    showGesture(getString(R.string.seek_by, "+${preferences.seekStepSeconds}"))
                }
                else -> session.togglePlay()
            }
            return true
        }

        override fun onScroll(start: MotionEvent?, current: MotionEvent, dx: Float, dy: Float): Boolean {
            if (!preferences.gestures || locked || start == null) return false
            val totalX = current.x - start.x
            val totalY = current.y - start.y
            if (mode == MODE_NONE) {
                // The screen's edges belong to Android's own back and notification gestures.
                val edge = EDGE_DP * resources.displayMetrics.density
                if (start.y < edge || start.y > area.height - edge || start.x < edge || start.x > area.width - edge) {
                    return false
                }
                if (abs(totalX) < SLOP_DP * resources.displayMetrics.density &&
                    abs(totalY) < SLOP_DP * resources.displayMetrics.density
                ) {
                    return false
                }
                mode = when {
                    abs(totalX) > abs(totalY) -> MODE_SEEK
                    start.x > area.width / 2 -> MODE_VOLUME
                    else -> MODE_BRIGHTNESS
                }
                startPosition = session.positionMs
                startVolume = session.volume
                startBrightness = currentBrightness()
            }
            when (mode) {
                MODE_SEEK -> {
                    val delta = (totalX / area.width * SEEK_GESTURE_SPAN_MS).toLong()
                    val target = PlaybackRules.seekTarget(startPosition, delta, session.durationMs)
                    session.seekTo(target)
                    showGesture(PlaybackRules.formatTime(target))
                }
                MODE_VOLUME -> {
                    val delta = (-totalY / area.height * session.volumeMaximum).toInt()
                    session.setVolumeLevel(startVolume + delta)
                    showVolume()
                    showGesture(getString(R.string.volume_level, session.volume))
                }
                MODE_BRIGHTNESS -> {
                    val value = (startBrightness - totalY / area.height).coerceIn(0.01f, 1f)
                    window.attributes = window.attributes.apply { screenBrightness = value }
                    showGesture(getString(R.string.brightness_level, (value * 100).toInt()))
                }
            }
            return true
        }
    }

    private fun currentBrightness(): Float {
        val set = window.attributes.screenBrightness
        if (set >= 0) return set
        return try {
            Settings.System.getInt(contentResolver, Settings.System.SCREEN_BRIGHTNESS) / 255f
        } catch (_: Settings.SettingNotFoundException) {
            0.5f
        }
    }

    private fun showGesture(text: String) {
        gestureLabel.text = text
        gestureLabel.visibility = View.VISIBLE
        handler.removeCallbacks(hideGestureLabel)
        handler.postDelayed(hideGestureLabel, GESTURE_LABEL_MS)
    }

    private fun bindViews() {
        video = findViewById(R.id.videoView)
        controls = findViewById(R.id.controls)
        messageLabel = findViewById(R.id.messageLabel)
        gestureLabel = findViewById(R.id.gestureLabel)
        titleLabel = findViewById(R.id.titleLabel)
        seekBar = findViewById(R.id.seekBar)
        positionLabel = findViewById(R.id.positionLabel)
        durationLabel = findViewById(R.id.durationLabel)
        playButton = findViewById(R.id.playButton)
        previousButton = findViewById(R.id.previousButton)
        nextButton = findViewById(R.id.nextButton)
        speedButton = findViewById(R.id.speedButton)
        volumeButton = findViewById(R.id.volumeButton)
        previewImage = findViewById(R.id.previewImage)
        pictureButton = findViewById(R.id.pictureButton)
        repeatButton = findViewById(R.id.repeatButton)
        unlockButton = findViewById(R.id.unlockButton)
        audioView = findViewById(R.id.audioView)
        audioArt = findViewById(R.id.audioArt)
        audioFade = findViewById(R.id.audioFade)
        audioInfo = findViewById(R.id.audioInfo)
        bottomBar = findViewById(R.id.bottomBar)
        toolRow = findViewById(R.id.toolRow)
        transportRow = findViewById(R.id.transportRow)
        shuffleButton = findViewById(R.id.shuffleButton)
        favouriteButton = findViewById(R.id.favouriteButton)
        backSeek = findViewById(R.id.backButton)
        forwardSeek = findViewById(R.id.forwardButton)
        placeInVideo = listOf(backSeek, forwardSeek, repeatButton, transportRow).map { view ->
            val parent = view.parent as ViewGroup
            Placed(view, parent, parent.indexOfChild(view), view.layoutParams)
        }
        shuffleButton.setOnClickListener { pressShuffle() }
        favouriteButton.setOnClickListener { pressFavourite() }
        findViewById<View>(R.id.equalizerButton).setOnClickListener { showEqualizer() }
        findViewById<View>(R.id.queueButton).setOnClickListener { showQueue() }
        bottomBar.addOnLayoutChangeListener { _, _, top, _, _, _, oldTop, _, _ ->
            if (top != oldTop) bottomBar.post { placeAudioCover() }
        }
        audioCover = findViewById(R.id.audioCover)
        audioBars = findViewById(R.id.audioBars)
        audioBars.style = preferences.visualStyle
        audioTitle = findViewById(R.id.audioTitle)
        audioArtist = findViewById(R.id.audioArtist)
        unlockButton.setOnClickListener { setLocked(false) }
        applySystemBarPadding(findViewById(R.id.topBar), includeBottom = false)
        applySystemBarPadding(findViewById(R.id.bottomBar), includeTop = false)

        val layer = findViewById<View>(R.id.gestureLayer)
        val detector = GestureDetector(this, Gestures(layer))
        layer.setOnTouchListener { view, event ->
            val handled = detector.onTouchEvent(event)
            if (event.action == MotionEvent.ACTION_UP) view.performClick()
            handled
        }
        layer.setOnClickListener { }
        video.addOnLayoutChangeListener { _, left, top, right, bottom, _, _, _, _ ->
            session.engine?.setWindowSize(right - left, bottom - top)
            applyTransform()
        }
        val stepSeconds = preferences.seekStepSeconds
        val backButton = findViewById<Button>(R.id.backButton)
        val forwardButton = findViewById<Button>(R.id.forwardButton)
        backButton.text = stepSeconds.toString()
        forwardButton.text = stepSeconds.toString()
        backButton.contentDescription = getString(R.string.back_label, stepSeconds)
        forwardButton.contentDescription = getString(R.string.forward_label, stepSeconds)
        backButton.setOnClickListener { seekBy(-preferences.seekStepSeconds * 1000L) }
        forwardButton.setOnClickListener { seekBy(preferences.seekStepSeconds * 1000L) }
        playButton.setOnClickListener {
            session.togglePlay()
            messageLabel.visibility = View.GONE
        }
        previousButton.setOnClickListener { session.previous() }
        nextButton.setOnClickListener { session.next() }
        findViewById<View>(R.id.closeButton).setOnClickListener { finish() }
        pictureButton.setOnClickListener { enterPicture() }
        findViewById<View>(R.id.fitButton).setOnClickListener { toggleFill() }
        findViewById<View>(R.id.rotateButton).setOnClickListener { toggleOrientation() }
        findViewById<View>(R.id.audioButton).setOnClickListener { showTracks(TrackKind.AUDIO) }
        findViewById<View>(R.id.subtitleButton).setOnClickListener { showTracks(TrackKind.SUBTITLE) }
        speedButton.setOnClickListener { showSpeed() }
        repeatButton.setOnClickListener { pressRepeat() }
        volumeButton.setOnClickListener { showVolumeDialog() }
        volumeButton.addOnLayoutChangeListener { _, left, _, right, _, oldLeft, _, oldRight, _ ->
            if (right - left != oldRight - oldLeft) volumeButton.post { centreVolumeContent() }
        }
        findViewById<View>(R.id.moreButton).setOnClickListener { showMore() }
        seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(bar: SeekBar, progress: Int, fromUser: Boolean) {
                val duration = session.durationMs
                if (fromUser && duration != null) {
                    val target = progress * duration / bar.max
                    positionLabel.text = PlaybackRules.formatTime(target)
                    requestPreview(target)
                }
            }

            override fun onStartTrackingTouch(bar: SeekBar) {
                userSeeking = true
            }

            override fun onStopTrackingTouch(bar: SeekBar) {
                userSeeking = false
                previewImage.visibility = View.GONE
                val duration = session.durationMs ?: return
                session.seekTo(bar.progress * duration / bar.max)
                scheduleHideControls()
            }
        })
    }

    companion object {
        const val EXTRA_QUEUE_URIS = "com.babarify.frame.QUEUE_URIS"
        const val EXTRA_QUEUE_TITLES = "com.babarify.frame.QUEUE_TITLES"
        const val EXTRA_QUEUE_INDEX = "com.babarify.frame.QUEUE_INDEX"
        const val EXTRA_SHUFFLE = "com.babarify.frame.SHUFFLE"

        /** A queue too big for an Intent, handed over by the screen that opens this one. */
        var pendingQueue: List<QueueItem>? = null
        @SuppressLint("StaticFieldLeak") // Cleared as the screen stops.
        private var visibleScreen: PlayerActivity? = null
        val isVisible: Boolean get() = visibleScreen != null
        var isInFront = false
            private set
        var closeRequested: (() -> Unit)? = null
            private set

        private const val REQUEST_SUBTITLE = 2
        private const val TICK_MS = 500L
        private const val HIDE_CONTROLS_MS = 4_000L
        private const val GESTURE_LABEL_MS = 800L
        private const val FADE_MS = 150L
        private const val UNLOCK_VISIBLE_MS = 3_000L
        private const val MS_PER_MINUTE = 60_000L
        private const val MIN_COVER_DP = 96
        private const val ICON_DP = 48
        private const val MATCH = LinearLayout.LayoutParams.MATCH_PARENT
        private const val WRAP = LinearLayout.LayoutParams.WRAP_CONTENT
        private const val DISABLED_ALPHA = 0.4f
        private const val TRANSPARENT_MASK = 0x00FFFFFF
        private const val FAVOURITE_COLOUR = 0xFFFB7185.toInt()
        private const val SAVED_QUEUE_AROUND = 200
        private val SLEEP_MINUTES = listOf(15, 30, 45, 60, 90, 120)

        @Suppress("DEPRECATION")
        private const val LAYOUT_BEHIND_BARS = View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN

        @Suppress("DEPRECATION")
        private const val HIDE_BARS = View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        private const val SEEK_GESTURE_SPAN_MS = 120_000L
        private const val EDGE_DP = 32
        private const val SLOP_DP = 16
        private const val MODE_NONE = 0
        private const val MODE_SEEK = 1
        private const val MODE_VOLUME = 2
        private const val MODE_BRIGHTNESS = 3
        private const val ZOOM_FIT = 1f
        private const val ZOOM_FILL = -1f
        private const val PREVIEW_WIDTH = 320
        private const val PREVIEW_HEIGHT = 180
        private const val STATE_URI = "uri"
        private const val STATE_TITLE = "title"
        private const val STATE_SUBTITLE = "subtitle"
        private const val STATE_POSITION = "position"
        private const val STATE_PLAYING = "playing"
        private const val STATE_QUEUE_URIS = "queue_uris"
        private const val STATE_QUEUE_TITLES = "queue_titles"
        private const val STATE_QUEUE_INDEX = "queue_index"
    }
}
