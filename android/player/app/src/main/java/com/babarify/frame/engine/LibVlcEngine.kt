package com.babarify.frame.engine

import android.content.Context
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.util.Log
import android.view.TextureView
import com.babarify.frame.core.ChapterInfo
import com.babarify.frame.core.EqualizerSettings
import com.babarify.frame.core.ErrorCode
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.core.TrackInfo
import com.babarify.frame.core.TrackKind
import java.io.File
import java.io.FileNotFoundException
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.interfaces.IMedia

/** Events arrive on the thread that created this engine, which must be the main thread. */
class LibVlcEngine(
    context: Context,
    private val options: EngineOptions,
    private val listener: EngineListener,
) : PlayerEngine {
    private val appContext = context.applicationContext
    private val libVlc = LibVLC(appContext, arguments(options))
    private val player = MediaPlayer(libVlc)
    private var descriptor: ParcelFileDescriptor? = null
    private var seekTarget: Long? = null

    override var state = PlaybackState.READY
        private set
    override var progressed = false
        private set
    override val positionMs: Long
        // A paused player sends no time updates, so report an accepted seek until it lands (R21).
        get() = seekTarget ?: player.time.coerceAtLeast(0)
    override val durationMs: Long?
        get() = player.length.takeIf { it > 0 }
    override val videoSize: Pair<Int, Int>?
        get() = player.currentVideoTrack?.takeIf { it.width > 0 && it.height > 0 }?.let { it.width to it.height }
    override val volume: Int
        get() = player.volume
    override val hasVideoTrack: Boolean
        get() = player.videoTracksCount > 0
    override var openedWithoutVideo = false
        private set

    init {
        player.setEventListener { event ->
            when (event.type) {
                MediaPlayer.Event.Opening -> update(PlaybackState.LOADING)
                MediaPlayer.Event.Playing -> update(PlaybackState.PLAYING)
                MediaPlayer.Event.Paused -> update(PlaybackState.PAUSED)
                MediaPlayer.Event.TimeChanged -> {
                    // libVLC reports 0 just after opening at a later position: not real progress.
                    if (event.timeChanged > 0) {
                        seekTarget = null
                        progressed = true
                    }
                }
                MediaPlayer.Event.ESAdded, MediaPlayer.Event.ESDeleted, MediaPlayer.Event.ESSelected ->
                    listener.onTracksChanged()
                MediaPlayer.Event.EndReached -> {
                    val end = PlaybackRules.classifyEnd(progressed)
                    update(end, if (end == PlaybackState.ERROR) ErrorCode.MEDIA_OPEN_FAILED else null)
                }
                MediaPlayer.Event.EncounteredError -> update(PlaybackState.ERROR, ErrorCode.MEDIA_OPEN_FAILED)
            }
        }
    }

    private fun update(new: PlaybackState, error: ErrorCode? = null) {
        Log.d(TAG, "state $new $error")
        state = new
        listener.onStateChanged(new, error)
    }

    override fun attachVideo(view: TextureView) {
        val vout = player.vlcVout
        if (vout.areViewsAttached()) vout.detachViews()
        vout.setVideoView(view)
        vout.attachViews()
        if (view.width > 0) setWindowSize(view.width, view.height)
        if (videoDetached) {
            videoDetached = false
            player.setVideoTrackEnabled(true)
        }
    }

    private var videoDetached = false

    override fun detachVideo() {
        videoDetached = true
        player.setVideoTrackEnabled(false)
        player.vlcVout.detachViews()
    }

    override fun setWindowSize(width: Int, height: Int) {
        player.vlcVout.setWindowSize(width, height)
    }

    override fun open(media: Uri, subtitle: File?, startMs: Long, startPaused: Boolean, withVideo: Boolean) {
        val fd = try {
            appContext.contentResolver.openFileDescriptor(media, "r")
        } catch (e: FileNotFoundException) {
            throw MediaAccessException(e)
        } catch (e: SecurityException) {
            // Permission to the file was lost, for example after it moved or was only lent to us.
            throw MediaAccessException(e)
        } ?: throw MediaAccessException(FileNotFoundException(media.toString()))
        descriptor = fd

        val item = Media(libVlc, fd.fileDescriptor)
        item.setHWDecoderEnabled(options.hardwareDecoding, false)
        if (startMs > 0) item.addOption(":start-time=${startMs / 1000.0}")
        if (startPaused) item.addOption(":start-paused")
        if (!withVideo) item.addOption(":no-video")
        openedWithoutVideo = !withVideo
        if (subtitle != null) {
            item.addSlave(IMedia.Slave(IMedia.Slave.Type.Subtitle, 4, Uri.fromFile(subtitle).toString()))
        }
        progressed = startMs > 0
        seekTarget = startMs.takeIf { it > 0 }
        update(PlaybackState.LOADING)
        player.media = item
        item.release()
        player.play()
    }

    override fun play() = player.play()

    override fun pause() {
        if (player.isPlaying) player.pause()
    }

    override fun seekTo(positionMs: Long) {
        seekTarget = positionMs
        player.time = positionMs
    }

    override fun tracks(kind: TrackKind): List<TrackInfo> {
        val (descriptions, current) = when (kind) {
            TrackKind.AUDIO -> player.audioTracks to player.audioTrack
            TrackKind.SUBTITLE -> player.spuTracks to player.spuTrack
        }
        return descriptions.orEmpty().map { TrackInfo(it.id, kind, it.name, it.id == current) }
    }

    override fun selectTrack(kind: TrackKind, id: Int) {
        when (kind) {
            TrackKind.AUDIO -> player.audioTrack = id
            TrackKind.SUBTITLE -> player.spuTrack = id
        }
    }

    override fun addSubtitle(file: File) {
        player.addSlave(IMedia.Slave.Type.Subtitle, Uri.fromFile(file), true)
    }

    override fun chapters(): List<ChapterInfo> =
        player.getChapters(-1).orEmpty().mapIndexed { index, chapter ->
            // libVLC can put a space in front of the name, as seen with Matroska chapters.
            ChapterInfo(chapter.name?.trim()?.ifEmpty { null } ?: "Chapter ${index + 1}", chapter.timeOffset)
        }

    override fun setRate(rate: Float) = player.setRate(rate)

    override fun setVolume(level: Int) {
        player.volume = level
    }

    // libVLC counts delays in microseconds.
    override fun setAudioDelay(delayMs: Long) {
        player.setAudioDelay(delayMs * 1000)
    }

    override fun setSubtitleDelay(delayMs: Long) {
        player.setSpuDelay(delayMs * 1000)
    }

    override fun setAspectRatio(ratio: String) {
        player.aspectRatio = ratio.ifEmpty { null }
    }

    override fun setEqualizer(settings: EqualizerSettings) {
        if (!settings.enabled) {
            player.setEqualizer(null)
            return
        }
        val equalizer = MediaPlayer.Equalizer.create()
        equalizer.setPreAmp(settings.preampDb)
        settings.bandsDb.forEachIndexed { band, db -> equalizer.setAmp(band, db) }
        player.setEqualizer(equalizer)
    }

    override fun equalizerPresets(): List<String> =
        List(MediaPlayer.Equalizer.getPresetCount()) { MediaPlayer.Equalizer.getPresetName(it) }

    override fun equalizerPreset(index: Int): EqualizerSettings {
        val preset = MediaPlayer.Equalizer.createFromPreset(index)
        return EqualizerSettings(
            true,
            preset.preAmp,
            List(EqualizerSettings.BAND_COUNT) { preset.getAmp(it) },
        ).normalized()
    }

    override fun equalizerBandFrequencies(): List<Float> =
        List(MediaPlayer.Equalizer.getBandCount()) { MediaPlayer.Equalizer.getBandFrequency(it) }

    override fun stats(): EngineStats? {
        val media = player.media ?: return null
        return try {
            media.stats?.let { EngineStats(it.decodedVideo, it.lostPictures, it.decodedAudio, it.lostAbuffers) }
        } finally {
            media.release()
        }
    }

    override fun release() {
        player.setEventListener(null)
        if (state == PlaybackState.LOADING) {
            // Stopping waits for libVLC, which can be building its font cache (~22 s, seen on a
            // Galaxy A33). Never make the screen wait for that: finish on another thread.
            player.vlcVout.detachViews()
            Thread { stopAndFree() }.start()
        } else {
            player.stop()
            player.vlcVout.detachViews()
            stopAndFree()
        }
    }

    private fun stopAndFree() {
        player.stop()
        player.release()
        libVlc.release()
        descriptor?.close()
        descriptor = null
    }

    private companion object {
        const val TAG = "BabarifyEngine"

        /** Subtitle looks are engine-wide options, so changing one restarts the engine, as on desktop. */
        fun arguments(options: EngineOptions): ArrayList<String> {
            val style = options.subtitleStyle.normalized()
            return arrayListOf(
                "--no-lua", // Matches the desktop engine's hardening (R34).
                "--sub-text-scale=${style.sizePct}",
                "--freetype-color=${style.textColor}",
                "--freetype-background-opacity=${style.backgroundOpacity * 255 / 100}",
                "--freetype-background-color=0",
            )
        }
    }
}
