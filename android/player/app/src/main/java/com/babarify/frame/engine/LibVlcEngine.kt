package com.babarify.frame.engine

import android.content.Context
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.util.Log
import android.view.SurfaceView
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
    private val context: Context,
    private val hardwareDecoding: Boolean,
    private val listener: EngineListener,
) : PlayerEngine {
    // --no-lua matches the desktop engine's hardening (R34).
    private val libVlc = LibVLC(context, arrayListOf("--no-lua"))
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

    override fun attach(surface: SurfaceView) {
        val vout = player.vlcVout
        vout.setVideoView(surface)
        vout.attachViews()
        if (surface.width > 0) setWindowSize(surface.width, surface.height)
    }

    override fun setWindowSize(width: Int, height: Int) {
        player.vlcVout.setWindowSize(width, height)
    }

    override fun open(media: Uri, subtitle: File?, startMs: Long, startPaused: Boolean) {
        val fd = try {
            context.contentResolver.openFileDescriptor(media, "r")
        } catch (e: FileNotFoundException) {
            throw MediaAccessException(e)
        } catch (e: SecurityException) {
            // Permission to the file was lost, for example after it moved or was only lent to us.
            throw MediaAccessException(e)
        } ?: throw MediaAccessException(FileNotFoundException(media.toString()))
        descriptor = fd

        val item = Media(libVlc, fd.fileDescriptor)
        item.setHWDecoderEnabled(hardwareDecoding, false)
        if (startMs > 0) item.addOption(":start-time=${startMs / 1000.0}")
        if (startPaused) item.addOption(":start-paused")
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
    }
}
