package com.babarify.frame.ui

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Shader
import android.os.SystemClock
import android.util.AttributeSet
import android.view.View
import com.babarify.frame.core.EqualizerAnimation
import com.babarify.frame.core.VisualStyle
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/**
 * Animation for audio with no picture of its own. It moves while the audio plays and rests when paused.
 * Decoration only: see [EqualizerAnimation].
 */
class EqualizerBarsView @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {
    private val density = resources.displayMetrics.density
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val strokes = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }
    private val wavePath = Path()
    private val levels = FloatArray(MAX_BARS) { EqualizerAnimation.REST }
    private val peaks = FloatArray(MAX_BARS) { EqualizerAnimation.REST }
    private val startedAt = SystemClock.elapsedRealtime()
    private var energy = 0f
    private var fade = 1f

    /** Moving now? False while paused, hidden, or when the phone is set to remove animations. */
    val animating: Boolean get() = playing && isShown && ValueAnimator.areAnimatorsEnabled()

    var playing = false
        set(value) {
            if (field != value) {
                field = value
                postInvalidateOnAnimation()
            }
        }

    /** The user's choice, which may be to move through them all. */
    var style = VisualStyle.AUTO
        set(value) {
            field = value
            postInvalidateOnAnimation()
        }

    /** What's on screen, never AUTO. */
    var shownStyle = VisualStyle.MIRROR
        private set

    override fun onSizeChanged(width: Int, height: Int, oldWidth: Int, oldHeight: Int) {
        val across = LinearGradient(0f, 0f, width.toFloat(), 0f, COLOURS, null, Shader.TileMode.CLAMP)
        paint.shader = across
        strokes.shader = across
    }

    override fun onDraw(canvas: Canvas) {
        val now = SystemClock.elapsedRealtime()
        val moving = animating
        val changing = moveTowardsChosenStyle(now)
        val count = barCount(shownStyle)
        var settling = changing
        val rest = restingLevel()
        for (bar in 0 until count) {
            val shape = if (shownStyle == VisualStyle.CIRCLE) 1f else EqualizerAnimation.envelope(bar, count)
            val target = if (moving) EqualizerAnimation.level(bar, now) * shape else rest
            levels[bar] += (target - levels[bar]) * EASE
            peaks[bar] = EqualizerAnimation.peak(peaks[bar], levels[bar])
            if (abs(target - levels[bar]) > SETTLED || peaks[bar] - levels[bar] > SETTLED) settling = true
        }
        val wanted = if (moving) 1f else REST_ENERGY
        energy += (wanted - energy) * EASE
        if (abs(wanted - energy) > SETTLED) settling = true
        when (shownStyle) {
            VisualStyle.CAPSULES -> drawCapsules(canvas, count)
            VisualStyle.WAVES -> drawWaves(canvas, now)
            VisualStyle.CIRCLE -> drawCircle(canvas, count, now)
            VisualStyle.LIGHTS -> drawLights(canvas, count)
            else -> drawMirror(canvas, count)
        }
        // Thirty frames a second is smooth enough, saves battery, and leaves the main thread idle
        // between frames: redrawing at full rate starved anything waiting for it to go idle.
        if (moving || settling) postInvalidateDelayed(FRAME_MS)
    }

    /** Fades out, changes style, and fades back in. True while that's still going on. */
    private fun moveTowardsChosenStyle(now: Long): Boolean {
        val chosen = if (style == VisualStyle.AUTO) EqualizerAnimation.autoStyle(now - startedAt) else style
        if (chosen != shownStyle) {
            fade -= FADE_STEP
            if (fade <= 0f) {
                fade = 0f
                shownStyle = chosen
            }
            return true
        }
        if (fade < 1f) {
            fade = (fade + FADE_STEP).coerceAtMost(1f)
            return true
        }
        return false
    }

    private fun barCount(shown: VisualStyle): Int = when (shown) {
        VisualStyle.CAPSULES -> 15
        VisualStyle.CIRCLE -> 48
        VisualStyle.LIGHTS -> 13
        else -> 19
    }

    private fun alpha(fraction: Float) = (255 * fraction * fade).toInt().coerceIn(0, 255)

    /** Solid bars with floating caps above a line, and their dimmer reflection below it. */
    private fun drawMirror(canvas: Canvas, count: Int) {
        val line = LINE_DP * density
        val base = height * MIRROR_BASE
        val up = base - line
        val down = height - base - line
        val margin = width * MIRROR_MARGIN
        val slot = (width - 2 * margin) / count
        val bar = slot * MIRROR_FILL
        val gap = CAP_GAP_DP * density
        for (index in 0 until count) {
            val left = margin + index * slot + (slot - bar) / 2
            val right = left + bar
            val height = levels[index] * up * MIRROR_REACH
            val peak = peaks[index] * up * MIRROR_REACH + gap
            val cap = (CAP_MIN_DP * density).coerceAtLeast(peaks[index] * CAP_DP * density)
            val below = down / up
            paint.alpha = alpha(1f)
            canvas.drawRect(left, base - height, right, base, paint)
            canvas.drawRect(left, base - peak - cap, right, base - peak, paint)
            paint.alpha = alpha(REFLECTION)
            canvas.drawRect(left, base + line, right, base + line + height * below, paint)
            canvas.drawRect(left, base + line + peak * below, right, base + line + (peak + cap) * below, paint)
        }
        paint.alpha = alpha(1f)
        canvas.drawRect(margin / 2, base, width - margin / 2, base + line, paint)
    }

    /** Rounded bars that grow from the middle in both directions. */
    private fun drawCapsules(canvas: Canvas, count: Int) {
        val slot = width.toFloat() / count
        val bar = slot * CAPSULE_FILL
        val middle = height / 2f
        paint.alpha = alpha(1f)
        for (index in 0 until count) {
            val left = index * slot + (slot - bar) / 2
            val half = (levels[index] * middle * CAPSULE_REACH).coerceAtLeast(bar / 2)
            canvas.drawRoundRect(left, middle - half, left + bar, middle + half, bar / 2, bar / 2, paint)
        }
    }

    /** Layers of smooth waves, each with a bright edge and a soft body. */
    private fun drawWaves(canvas: Canvas, now: Long) {
        val t = now / 1000f
        val middle = height / 2f
        strokes.strokeWidth = WAVE_LINE_DP * density
        for (layer in 0 until WAVE_LAYERS) {
            val offset = layer * WAVE_PHASE
            val reach = middle * WAVE_REACH * energy * (1f - layer * WAVE_SHRINK)
            wavePath.reset()
            var x = 0f
            val step = width / WAVE_STEPS.toFloat()
            for (point in 0..WAVE_STEPS) {
                val across = point.toFloat() / WAVE_STEPS
                val taper = sin(across * PI).toFloat()
                val wave = sin(across * 9f + t * 2.1f + offset) * 0.6f + sin(across * 17f - t * 3.3f + offset * 2) * 0.4f
                val y = middle - wave * reach * taper
                if (point == 0) wavePath.moveTo(x, y) else wavePath.lineTo(x, y)
                x += step
            }
            strokes.alpha = alpha(1f - layer * WAVE_DIM)
            canvas.drawPath(wavePath, strokes)
            wavePath.lineTo(width.toFloat(), middle)
            wavePath.lineTo(0f, middle)
            wavePath.close()
            paint.alpha = alpha(WAVE_BODY)
            canvas.drawPath(wavePath, paint)
        }
    }

    /** Rays around a ring that breathes. */
    private fun drawCircle(canvas: Canvas, count: Int, now: Long) {
        val centreX = width / 2f
        val centreY = height / 2f
        val space = min(width, height) / 2f
        val breath = sin(now / 700.0).toFloat() * CIRCLE_BREATH * energy
        val ring = space * (CIRCLE_RING + breath)
        strokes.strokeWidth = (2 * PI.toFloat() * ring / count) * CIRCLE_FILL
        strokes.alpha = alpha(1f)
        for (index in 0 until count) {
            val angle = 2 * PI * index / count - PI / 2
            val out = ring + levels[index] * (space - ring) * CIRCLE_REACH + strokes.strokeWidth
            val dx = cos(angle).toFloat()
            val dy = sin(angle).toFloat()
            canvas.drawLine(centreX + dx * ring, centreY + dy * ring, centreX + dx * out, centreY + dy * out, strokes)
        }
        paint.alpha = alpha(CIRCLE_CORE)
        canvas.drawCircle(centreX, centreY, ring * CIRCLE_CORE_SIZE, paint)
    }

    /** Columns of small lights, like a stereo's display. */
    private fun drawLights(canvas: Canvas, count: Int) {
        val slot = width.toFloat() / count
        val rows = (height / slot).toInt().coerceIn(LIGHTS_MIN_ROWS, LIGHTS_MAX_ROWS)
        val cell = height.toFloat() / rows
        val size = min(slot, cell) * LIGHT_FILL
        val corner = size * LIGHT_CORNER
        for (column in 0 until count) {
            val lit = (levels[column] * rows).toInt()
            val peak = (peaks[column] * rows).toInt()
            val x = column * slot + (slot - size) / 2
            for (row in 0 until rows) {
                val y = height - (row + 1) * cell + (cell - size) / 2
                paint.alpha = alpha(if (row < lit || row == peak) 1f else LIGHT_OFF)
                canvas.drawRoundRect(x, y, x + size, y + size, corner, corner, paint)
            }
        }
    }

    /** With animations removed, the bars still say "music" while standing still. */
    private fun restingLevel(): Float = if (playing && !ValueAnimator.areAnimatorsEnabled()) STILL_LEVEL else EqualizerAnimation.REST

    private companion object {
        val COLOURS = intArrayOf(
            0xFF5B62FF.toInt(),
            0xFF9D4BF2.toInt(),
            0xFFF12BD9.toInt(),
            0xFFFF5F9E.toInt(),
            0xFFFFA23E.toInt(),
        )
        const val MAX_BARS = 64
        const val FRAME_MS = 33L
        const val EASE = 0.3f
        const val SETTLED = 0.005f
        const val STILL_LEVEL = 0.4f
        const val REST_ENERGY = 0.12f
        const val FADE_STEP = 0.08f
        const val LINE_DP = 3f
        const val CAP_GAP_DP = 12f
        const val CAP_DP = 9f
        const val CAP_MIN_DP = 2f
        const val MIRROR_BASE = 0.56f
        const val MIRROR_MARGIN = 0.06f
        const val MIRROR_FILL = 0.74f
        const val MIRROR_REACH = 0.86f
        const val REFLECTION = 0.34f
        const val CAPSULE_FILL = 0.58f
        const val CAPSULE_REACH = 0.94f
        const val WAVE_LAYERS = 3
        const val WAVE_STEPS = 60
        const val WAVE_LINE_DP = 3f
        const val WAVE_PHASE = 1.4f
        const val WAVE_REACH = 0.8f
        const val WAVE_SHRINK = 0.22f
        const val WAVE_DIM = 0.28f
        const val WAVE_BODY = 0.16f
        const val CIRCLE_RING = 0.42f
        const val CIRCLE_BREATH = 0.03f
        const val CIRCLE_REACH = 0.86f
        const val CIRCLE_FILL = 0.6f
        const val CIRCLE_CORE = 0.2f
        const val CIRCLE_CORE_SIZE = 0.82f
        const val LIGHTS_MIN_ROWS = 6
        const val LIGHTS_MAX_ROWS = 22
        const val LIGHT_FILL = 0.76f
        const val LIGHT_CORNER = 0.22f
        const val LIGHT_OFF = 0.1f
    }
}
