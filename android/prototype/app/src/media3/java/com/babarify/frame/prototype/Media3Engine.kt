package com.babarify.frame.prototype

import android.content.Context
import android.net.Uri
import android.os.SystemClock
import android.view.SurfaceView
import androidx.annotation.OptIn
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.Tracks
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.analytics.AnalyticsListener

fun createEngine(context: Context, probe: ProbeSink): PlayerEngine = Media3Engine(context, probe)

@OptIn(UnstableApi::class)
private class Media3Engine(context: Context, private val probe: ProbeSink) : PlayerEngine {
    private val player = ExoPlayer.Builder(context).build()
    private var openedAt = 0L
    private var droppedFrames = 0

    override val name = "media3"
    override val positionMs get() = player.currentPosition
    override val durationMs get() = player.duration.coerceAtLeast(0)
    override val isPlaying get() = player.playWhenReady

    init {
        player.addAnalyticsListener(object : AnalyticsListener {
            override fun onRenderedFirstFrame(
                eventTime: AnalyticsListener.EventTime,
                output: Any,
                renderTimeMs: Long,
            ) {
                probe.event("first_frame", mapOf("after_ms" to SystemClock.elapsedRealtime() - openedAt))
            }

            override fun onVideoDecoderInitialized(
                eventTime: AnalyticsListener.EventTime,
                decoderName: String,
                initializedTimestampMs: Long,
                initializationDurationMs: Long,
            ) {
                probe.event("video_decoder", mapOf("name" to decoderName))
            }

            override fun onAudioDecoderInitialized(
                eventTime: AnalyticsListener.EventTime,
                decoderName: String,
                initializedTimestampMs: Long,
                initializationDurationMs: Long,
            ) {
                probe.event("audio_decoder", mapOf("name" to decoderName))
            }

            override fun onDroppedVideoFrames(
                eventTime: AnalyticsListener.EventTime,
                droppedFrames: Int,
                elapsedMs: Long,
            ) {
                this@Media3Engine.droppedFrames += droppedFrames
            }
        })
        player.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                probe.event("error", mapOf("code" to error.errorCodeName, "message" to error.message))
            }

            override fun onTracksChanged(tracks: Tracks) {
                probe.event("tracks", mapOf("tracks" to describe(tracks)))
            }

            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) {
                    probe.event(
                        "ended",
                        mapOf("position_ms" to positionMs, "dropped_frames" to droppedFrames),
                    )
                }
            }
        })
    }

    override fun attach(surface: SurfaceView) = player.setVideoSurfaceView(surface)

    override fun open(media: Uri, subtitle: Uri?, startMs: Long) {
        val item = MediaItem.Builder().setUri(media)
        if (subtitle != null) {
            val mime = if (subtitle.toString().endsWith(".ass")) MimeTypes.TEXT_SSA else MimeTypes.APPLICATION_SUBRIP
            item.setSubtitleConfigurations(
                listOf(
                    MediaItem.SubtitleConfiguration.Builder(subtitle)
                        .setMimeType(mime)
                        .setSelectionFlags(C.SELECTION_FLAG_DEFAULT)
                        .build(),
                ),
            )
        }
        openedAt = SystemClock.elapsedRealtime()
        player.setMediaItem(item.build(), startMs)
        player.prepare()
    }

    override fun play() {
        player.playWhenReady = true
    }

    override fun pause() {
        player.playWhenReady = false
    }

    override fun seekTo(positionMs: Long) = player.seekTo(positionMs)

    override fun release() {
        probe.event("stats", mapOf("position_ms" to positionMs, "dropped_frames" to droppedFrames))
        player.release()
    }

    private fun describe(tracks: Tracks): List<String> = tracks.groups.flatMap { group ->
        (0 until group.length).map { index ->
            val format = group.getTrackFormat(index)
            "${format.sampleMimeType} supported=${group.isTrackSupported(index)} " +
                "selected=${group.isTrackSelected(index)} lang=${format.language}"
        }
    }
}
