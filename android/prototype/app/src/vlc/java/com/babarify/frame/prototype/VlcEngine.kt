package com.babarify.frame.prototype

import android.content.Context
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.view.SurfaceView
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.interfaces.IMedia

fun createEngine(context: Context, probe: ProbeSink): PlayerEngine = VlcEngine(context, probe)

private class VlcEngine(private val context: Context, private val probe: ProbeSink) : PlayerEngine {
    // --no-lua matches the desktop engine's hardening (R34); --stats feeds the frame counts below.
    private val libVlc = LibVLC(context, arrayListOf("--no-lua", "--stats"))
    private val player = MediaPlayer(libVlc)
    private var media: Media? = null
    private var descriptor: ParcelFileDescriptor? = null
    private var openedAt = 0L
    private var firstFrameSeen = false

    override val name = "libvlc"
    override val positionMs get() = player.time.coerceAtLeast(0)
    override val durationMs get() = player.length.coerceAtLeast(0)
    override val isPlaying get() = player.isPlaying

    init {
        player.setEventListener { event ->
            when (event.type) {
                MediaPlayer.Event.Vout -> if (event.voutCount > 0 && !firstFrameSeen) {
                    firstFrameSeen = true
                    probe.event("first_frame", mapOf("after_ms" to SystemClock.elapsedRealtime() - openedAt))
                    probe.event("tracks", mapOf("tracks" to describeTracks()))
                }
                MediaPlayer.Event.EncounteredError -> probe.event("error", mapOf("message" to "EncounteredError"))
                MediaPlayer.Event.EndReached -> probe.event("ended", stats())
            }
        }
    }

    override fun attach(surface: SurfaceView) {
        val vout = player.vlcVout
        vout.setVideoView(surface)
        surface.post {
            vout.setWindowSize(surface.width, surface.height)
        }
        vout.attachViews()
    }

    override fun open(media: Uri, subtitle: Uri?, startMs: Long) {
        // The picker returns content:// addresses, which libVLC reads through a descriptor.
        val item = if (media.scheme == "content") {
            val fd = context.contentResolver.openFileDescriptor(media, "r")
                ?: error("no descriptor for picked file")
            descriptor = fd
            Media(libVlc, fd.fileDescriptor)
        } else {
            Media(libVlc, media)
        }
        item.setHWDecoderEnabled(true, false)
        if (startMs > 0) item.addOption(":start-time=${startMs / 1000.0}")
        if (subtitle != null) item.addSlave(IMedia.Slave(IMedia.Slave.Type.Subtitle, 4, subtitle.toString()))
        this.media = item
        openedAt = SystemClock.elapsedRealtime()
        player.media = item
        item.release()
    }

    override fun play() = player.play()

    override fun pause() {
        if (player.isPlaying) player.pause()
    }

    override fun seekTo(positionMs: Long) {
        player.time = positionMs
    }

    override fun release() {
        probe.event("stats", stats())
        player.setEventListener(null)
        player.stop()
        player.vlcVout.detachViews()
        player.release()
        libVlc.release()
        descriptor?.close()
    }

    private fun stats(): Map<String, Any?> {
        val current = player.media?.stats
        return mapOf(
            "position_ms" to positionMs,
            "dropped_frames" to current?.lostPictures,
            "displayed_frames" to current?.displayedPictures,
            "decoded_video" to current?.decodedVideo,
        )
    }

    private fun describeTracks(): List<String> {
        val video = player.videoTracks.orEmpty().map { "video ${it.name}" }
        val audio = player.audioTracks.orEmpty().map { "audio ${it.name}" }
        val text = player.spuTracks.orEmpty().map { "text ${it.name}" }
        return video + audio + text
    }
}
