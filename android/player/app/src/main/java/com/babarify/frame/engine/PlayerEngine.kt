package com.babarify.frame.engine

import android.net.Uri
import android.view.SurfaceView
import com.babarify.frame.core.ErrorCode
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.core.TrackInfo
import com.babarify.frame.core.TrackKind
import java.io.File

/** Everything the UI needs from a playback engine; only LibVlcEngine knows about libVLC. */
interface PlayerEngine {
    val state: PlaybackState
    val progressed: Boolean
    val positionMs: Long
    val durationMs: Long?

    fun attach(surface: SurfaceView)
    fun setWindowSize(width: Int, height: Int)

    /** Throws [MediaAccessException] when the file cannot be reached. */
    fun open(media: Uri, subtitle: File?, startMs: Long, startPaused: Boolean)
    fun play()
    fun pause()
    fun seekTo(positionMs: Long)
    fun tracks(kind: TrackKind): List<TrackInfo>
    fun selectTrack(kind: TrackKind, id: Int)
    fun addSubtitle(file: File)
    fun release()
}

interface EngineListener {
    fun onStateChanged(state: PlaybackState, error: ErrorCode?)
    fun onTracksChanged()
}

class MediaAccessException(cause: Exception) : Exception(cause)
