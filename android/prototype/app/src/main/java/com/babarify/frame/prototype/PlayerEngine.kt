package com.babarify.frame.prototype

import android.net.Uri
import android.view.SurfaceView

/** What the prototype needs from a playback engine; each flavor provides one `createEngine`. */
interface PlayerEngine {
    val name: String
    val positionMs: Long
    val durationMs: Long
    val isPlaying: Boolean

    fun attach(surface: SurfaceView)
    fun open(media: Uri, subtitle: Uri?, startMs: Long)
    fun play()
    fun pause()
    fun seekTo(positionMs: Long)
    fun release()
}

/** Receives measurements from an engine; values must be JSON-safe (numbers, strings, lists). */
fun interface ProbeSink {
    fun event(name: String, fields: Map<String, Any?>)
}
