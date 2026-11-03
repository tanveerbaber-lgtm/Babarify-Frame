package com.babarify.frame.core

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * Picture settings use the desktop app's meanings: 1.0 leaves brightness, contrast and saturation
 * unchanged, and hue is in degrees. Applied to the video view as a colour matrix, so it works with
 * hardware decoding and needs no restart. Desktop's gamma can't be expressed as a matrix.
 */
data class PictureSettings(
    val brightness: Float = 1f,
    val contrast: Float = 1f,
    val saturation: Float = 1f,
    val hue: Float = 0f,
) {
    val isDefault: Boolean get() = normalized() == PictureSettings()

    fun normalized() = PictureSettings(
        brightness.coerceIn(0f, 2f),
        contrast.coerceIn(0f, 2f),
        saturation.coerceIn(0f, 3f),
        hue.coerceIn(-180f, 180f),
    )

    /** A 4x5 matrix in android.graphics.ColorMatrix order, with colours in 0..255. */
    fun colorMatrix(): FloatArray {
        val p = normalized()
        val brightness = floatArrayOf(
            p.brightness, 0f, 0f, 0f, 0f,
            0f, p.brightness, 0f, 0f, 0f,
            0f, 0f, p.brightness, 0f, 0f,
            0f, 0f, 0f, 1f, 0f,
        )
        val shift = 127.5f * (1f - p.contrast)
        val contrast = floatArrayOf(
            p.contrast, 0f, 0f, 0f, shift,
            0f, p.contrast, 0f, 0f, shift,
            0f, 0f, p.contrast, 0f, shift,
            0f, 0f, 0f, 1f, 0f,
        )
        return multiply(multiply(brightness, contrast), multiply(saturationMatrix(p.saturation), hueMatrix(p.hue)))
    }

    private fun saturationMatrix(s: Float): FloatArray {
        val r = LUMA_R * (1 - s)
        val g = LUMA_G * (1 - s)
        val b = LUMA_B * (1 - s)
        return floatArrayOf(
            r + s, g, b, 0f, 0f,
            r, g + s, b, 0f, 0f,
            r, g, b + s, 0f, 0f,
            0f, 0f, 0f, 1f, 0f,
        )
    }

    private fun hueMatrix(degrees: Float): FloatArray {
        val radians = degrees * PI.toFloat() / 180f
        val c = cos(radians)
        val s = sin(radians)
        return floatArrayOf(
            LUMA_R + c * (1 - LUMA_R) - s * LUMA_R,
            LUMA_G - c * LUMA_G - s * LUMA_G,
            LUMA_B - c * LUMA_B + s * (1 - LUMA_B),
            0f,
            0f,
            LUMA_R - c * LUMA_R + s * 0.143f,
            LUMA_G + c * (1 - LUMA_G) + s * 0.140f,
            LUMA_B - c * LUMA_B - s * 0.283f,
            0f,
            0f,
            LUMA_R - c * LUMA_R - s * (1 - LUMA_R),
            LUMA_G - c * LUMA_G + s * LUMA_G,
            LUMA_B + c * (1 - LUMA_B) + s * LUMA_B,
            0f,
            0f,
            0f, 0f, 0f, 1f, 0f,
        )
    }

    private fun multiply(a: FloatArray, b: FloatArray): FloatArray {
        val out = FloatArray(20)
        for (row in 0 until 4) {
            for (column in 0 until 5) {
                var sum = if (column == 4) a[row * 5 + 4] else 0f
                for (k in 0 until 4) sum += a[row * 5 + k] * b[k * 5 + column]
                out[row * 5 + column] = sum
            }
        }
        return out
    }

    private companion object {
        const val LUMA_R = 0.213f
        const val LUMA_G = 0.715f
        const val LUMA_B = 0.072f
    }
}

/** Amplification in dB, -20 to +20, in libVLC's ten bands, as on desktop. */
data class EqualizerSettings(
    val enabled: Boolean = false,
    val preampDb: Float = 0f,
    val bandsDb: List<Float> = List(BAND_COUNT) { 0f },
) {
    fun normalized() = EqualizerSettings(
        enabled,
        preampDb.coerceIn(MIN_DB, MAX_DB),
        List(BAND_COUNT) { (bandsDb.getOrElse(it) { 0f }).coerceIn(MIN_DB, MAX_DB) },
    )

    companion object {
        const val BAND_COUNT = 10
        const val MIN_DB = -20f
        const val MAX_DB = 20f
    }
}

data class EnhancementProfile(val name: String, val picture: PictureSettings, val equalizer: EqualizerSettings) {
    companion object {
        const val MAX_PROFILES = 20
        const val MAX_NAME = 60
    }
}

enum class VideoTransform(val rotation: Float, val flipX: Boolean, val flipY: Boolean) {
    NONE(0f, false, false),
    ROTATE_90(90f, false, false),
    ROTATE_180(180f, false, false),
    ROTATE_270(270f, false, false),
    FLIP_HORIZONTAL(0f, true, false),
    FLIP_VERTICAL(0f, false, true),
}

/** How the video view is turned and scaled; the video itself stays where libVLC put it. */
data class ViewTransform(val rotation: Float, val scaleX: Float, val scaleY: Float)

object VideoGeometry {
    /** A quarter turn must shrink the picture to keep it inside a view of the other shape. */
    fun viewTransform(transform: VideoTransform, zoom: Float, viewWidth: Int, viewHeight: Int): ViewTransform {
        val turned = transform.rotation == 90f || transform.rotation == 270f
        val fit = if (turned && viewWidth > 0 && viewHeight > 0) {
            min(viewWidth.toFloat() / viewHeight, viewHeight.toFloat() / viewWidth)
        } else {
            1f
        }
        val scale = fit * zoom
        return ViewTransform(
            transform.rotation,
            if (transform.flipX) -scale else scale,
            if (transform.flipY) -scale else scale,
        )
    }

    /** The zoom that makes a letterboxed video fill the view, cropping what no longer fits. */
    fun fillZoom(viewWidth: Int, viewHeight: Int, videoWidth: Int, videoHeight: Int): Float {
        if (viewWidth <= 0 || viewHeight <= 0 || videoWidth <= 0 || videoHeight <= 0) return 1f
        val widthRatio = viewWidth.toFloat() / videoWidth
        val heightRatio = viewHeight.toFloat() / videoHeight
        return max(widthRatio, heightRatio) / min(widthRatio, heightRatio)
    }
}
