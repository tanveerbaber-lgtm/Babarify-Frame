package com.babarify.frame.engine

import android.net.Uri
import android.view.TextureView
import com.babarify.frame.core.ChapterInfo
import com.babarify.frame.core.EqualizerSettings
import com.babarify.frame.core.ErrorCode
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.core.SubtitleStyle
import com.babarify.frame.core.TrackInfo
import com.babarify.frame.core.TrackKind
import java.io.File

data class EngineOptions(val hardwareDecoding: Boolean, val subtitleStyle: SubtitleStyle)

data class EngineStats(val decodedVideo: Int, val lostPictures: Int, val decodedAudio: Int, val lostAudio: Int)

/** Everything the app needs from a playback engine; only LibVlcEngine knows about libVLC. */
interface PlayerEngine {
    val state: PlaybackState
    val progressed: Boolean
    val positionMs: Long
    val durationMs: Long?
    val videoSize: Pair<Int, Int>?
    val volume: Int

    fun attachVideo(view: TextureView)

    /** Keeps the sound going with nothing to draw on. */
    fun detachVideo()
    fun setWindowSize(width: Int, height: Int)

    /** Throws [MediaAccessException] when the file cannot be reached. */
    fun open(media: Uri, subtitle: File?, startMs: Long, startPaused: Boolean)
    fun play()
    fun pause()
    fun seekTo(positionMs: Long)
    fun tracks(kind: TrackKind): List<TrackInfo>
    fun selectTrack(kind: TrackKind, id: Int)
    fun addSubtitle(file: File)
    fun chapters(): List<ChapterInfo>
    fun setRate(rate: Float)
    fun setVolume(level: Int)
    fun setAudioDelay(delayMs: Long)
    fun setSubtitleDelay(delayMs: Long)
    fun setAspectRatio(ratio: String)
    fun setEqualizer(settings: EqualizerSettings)
    fun equalizerPresets(): List<String>
    fun equalizerPreset(index: Int): EqualizerSettings
    fun equalizerBandFrequencies(): List<Float>
    fun stats(): EngineStats?
    fun release()
}

interface EngineListener {
    fun onStateChanged(state: PlaybackState, error: ErrorCode?)
    fun onTracksChanged()
}

class MediaAccessException(cause: Exception) : Exception(cause)
