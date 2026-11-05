package com.babarify.frame.core

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.sin

/** How songs with no picture are animated. AUTO moves through the others while a song plays. */
enum class VisualStyle { AUTO, MIRROR, CAPSULES, WAVES, CIRCLE, LIGHTS }

/**
 * How high each animated bar stands. This is decoration, not a measurement: reading the real sound
 * would need Android's microphone permission, which this app will not ask for.
 */
object EqualizerAnimation {
    const val REST = 0.08f
    const val AUTO_SWITCH_MS = 20_000L
    private const val PEAK_FALL = 0.012f
    private const val ENVELOPE_FLOOR = 0.45f

    /** The styles AUTO goes through. */
    val CYCLE: List<VisualStyle> = VisualStyle.entries.filter { it != VisualStyle.AUTO }

    /** A level from [REST] to 1, moving smoothly over [timeMs] and differently for each bar. */
    fun level(bar: Int, timeMs: Long): Float {
        val t = timeMs / 1000.0
        val wave = 0.55 * abs(sin(t * 2.3 + bar * 0.9)) +
            0.3 * abs(sin(t * 4.1 + bar * 1.7)) +
            0.15 * abs(sin(t * PI * 2.7 + bar * 2.9))
        return (REST + (1 - REST) * wave).toFloat().coerceIn(REST, 1f)
    }

    /** Taller in the middle and lower at the ends, so a row of bars makes a shape. From 0.45 to 1. */
    fun envelope(bar: Int, count: Int): Float {
        if (count <= 1) return 1f
        val across = bar.toDouble() / (count - 1)
        return (ENVELOPE_FLOOR + (1 - ENVELOPE_FLOOR) * sin(across * PI)).toFloat()
    }

    /** A peak jumps up with its bar and then falls slowly back to it. */
    fun peak(previous: Float, level: Float): Float = maxOf(level, previous - PEAK_FALL)

    /** Which style AUTO shows, this long after it started. */
    fun autoStyle(elapsedMs: Long): VisualStyle =
        CYCLE[((elapsedMs.coerceAtLeast(0) / AUTO_SWITCH_MS) % CYCLE.size).toInt()]
}
