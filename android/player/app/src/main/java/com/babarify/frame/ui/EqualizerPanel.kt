package com.babarify.frame.ui

import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Shader
import android.os.Bundle
import android.util.AttributeSet
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import com.babarify.frame.R
import com.babarify.frame.core.EqualizerSettings
import com.babarify.frame.core.MusicRules
import com.babarify.frame.data.Preferences
import com.babarify.frame.engine.PlayerEngine
import kotlin.math.atan2
import kotlin.math.min
import kotlin.math.roundToInt

/** A value from 0 to 1 that fingers and screen readers can both change. */
abstract class ValueControl @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {
    protected val density = resources.displayMetrics.density
    var value = 0f
        set(new) {
            field = new.coerceIn(0f, 1f)
            invalidate()
        }
    var onChange: ((Float) -> Unit)? = null
    var spoken: () -> String = { "${(value * 100).roundToInt()} %" }

    init {
        isFocusable = true
        isClickable = true
    }

    protected abstract fun valueAt(x: Float, y: Float): Float?

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!isEnabled) return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                valueAt(event.x, event.y)?.let(::userSet)
            }
            MotionEvent.ACTION_UP -> {
                parent?.requestDisallowInterceptTouchEvent(false)
                performClick()
            }
            MotionEvent.ACTION_CANCEL -> parent?.requestDisallowInterceptTouchEvent(false)
        }
        return true
    }

    fun userSet(new: Float) {
        value = new
        onChange?.invoke(value)
    }

    override fun getAccessibilityClassName(): CharSequence = SeekBar::class.java.name

    override fun onInitializeAccessibilityNodeInfo(info: AccessibilityNodeInfo) {
        super.onInitializeAccessibilityNodeInfo(info)
        info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD)
        info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD)
        info.rangeInfo = AccessibilityNodeInfo.RangeInfo.obtain(AccessibilityNodeInfo.RangeInfo.RANGE_TYPE_FLOAT, 0f, 1f, value)
        info.text = spoken()
    }

    override fun performAccessibilityAction(action: Int, arguments: Bundle?): Boolean {
        when (action) {
            AccessibilityNodeInfo.ACTION_SCROLL_FORWARD -> userSet(value + STEP)
            AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD -> userSet(value - STEP)
            else -> return super.performAccessibilityAction(action, arguments)
        }
        return true
    }

    private companion object {
        const val STEP = 0.05f
    }
}

/** An upright slider with its middle at zero, for one band of the equalizer. */
class BandSlider @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : ValueControl(context, attrs) {
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = context.themeColor(R.attr.borderColor)
        strokeCap = Paint.Cap.ROUND
        strokeWidth = 4 * density
    }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = context.themeColor(R.attr.accent2Color)
        strokeCap = Paint.Cap.ROUND
        strokeWidth = 4 * density
    }
    private val thumb = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = context.themeColor(R.attr.accent2Color) }
    private val radius get() = THUMB_DP * density

    override fun valueAt(x: Float, y: Float): Float = 1 - (y - radius) / (height - 2 * radius)

    override fun onDraw(canvas: Canvas) {
        val x = width / 2f
        val travel = height - 2 * radius
        val thumbY = radius + travel * (1 - value)
        val middle = height / 2f
        canvas.drawLine(x, radius, x, height - radius, track)
        canvas.drawLine(x, middle, x, thumbY, fill)
        canvas.drawCircle(x, thumbY, radius, thumb)
    }

    private companion object {
        const val THUMB_DP = 8
    }
}

/** A round dial with a coloured arc, turned with a finger. */
class DialControl @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : ValueControl(context, attrs) {
    private val arc = RectF()
    private val trackPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeWidth = 8 * density
        color = context.themeColor(R.attr.borderColor)
    }
    private val valuePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeWidth = 8 * density
    }
    private val knob = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = context.themeColor(R.attr.raisedColor) }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = context.themeColor(R.attr.inkColor)
        textAlign = Paint.Align.CENTER
        textSize = 18 * density
        isFakeBoldText = true
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        val inset = 8 * density
        arc.set(inset, inset, w - inset, h - inset)
        valuePaint.shader = LinearGradient(
            0f,
            h.toFloat(),
            w.toFloat(),
            0f,
            context.themeColor(R.attr.accentColor),
            context.themeColor(R.attr.accent2Color),
            Shader.TileMode.CLAMP,
        )
    }

    /** Clockwise from the gap at the bottom. The gap itself changes nothing, so the ends can't jump. */
    override fun valueAt(x: Float, y: Float): Float? {
        val degrees = Math.toDegrees(atan2((y - height / 2f).toDouble(), (x - width / 2f).toDouble())).toFloat()
        val fromStart = (degrees - START_DEGREES + 360) % 360
        return if (fromStart <= SWEEP_DEGREES) fromStart / SWEEP_DEGREES else null
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawCircle(width / 2f, height / 2f, min(width, height) / 2f - 20 * density, knob)
        canvas.drawArc(arc, START_DEGREES, SWEEP_DEGREES, false, trackPaint)
        if (value > 0) canvas.drawArc(arc, START_DEGREES, SWEEP_DEGREES * value, false, valuePaint)
        canvas.drawText(spoken(), width / 2f, height / 2f + label.textSize / 3, label)
    }

    private companion object {
        const val START_DEGREES = 135f
        const val SWEEP_DEGREES = 270f
    }
}

/** The equalizer, on a screen of its own. Every change applies at once. */
object EqualizerPanel {
    fun show(activity: Activity, preferences: Preferences, engine: PlayerEngine?, onChange: () -> Unit) {
        val dialog = Dialog(activity, R.style.Theme_Babarify_Panel)
        dialog.setContentView(R.layout.dialog_equalizer)
        val root = dialog.findViewById<View>(R.id.eqRoot)
        applySystemBarPadding(root)
        dialog.findViewById<View>(R.id.eqBack).setOnClickListener { dialog.dismiss() }
        Panel(dialog, activity, preferences, engine, onChange).build()
        dialog.show()
    }

    private class Panel(
        private val dialog: Dialog,
        private val activity: Activity,
        private val preferences: Preferences,
        private val engine: PlayerEngine?,
        private val onChange: () -> Unit,
    ) {
        private val density = activity.resources.displayMetrics.density
        private val enabled = dialog.findViewById<Switch>(R.id.eqEnabled)
        private val bass = dialog.findViewById<DialControl>(R.id.eqBass)
        private val preamp = dialog.findViewById<DialControl>(R.id.eqPreamp)
        private val sliders = ArrayList<BandSlider>()
        private val levels = ArrayList<TextView>()
        private val chips = ArrayList<TextView>()

        fun build() {
            enabled.isChecked = preferences.equalizer.enabled
            enabled.setOnCheckedChangeListener { _, on ->
                preferences.equalizer = preferences.equalizer.copy(enabled = on)
                onChange()
            }
            bands()
            presets()
            bass.value = preferences.equalizerBass
            bass.onChange = { dial ->
                val current = preferences.equalizer
                val moved = MusicRules.withBass(
                    current.bandsDb,
                    preferences.equalizerBass,
                    dial,
                    EqualizerSettings.MIN_DB,
                    EqualizerSettings.MAX_DB,
                )
                preferences.equalizerBass = dial
                changed(current.copy(bandsDb = moved))
                showAll()
            }
            preamp.spoken = { "%+.1f".format(dbFrom(preamp.value)) }
            bass.contentDescription = activity.getString(R.string.bass_boost)
            preamp.contentDescription = activity.getString(R.string.preamp)
            preamp.onChange = { dial ->
                changed(preferences.equalizer.copy(preampDb = dbFrom(dial)))
            }
            dialog.findViewById<View>(R.id.eqReset).setOnClickListener {
                preferences.equalizerBass = 0f
                preferences.equalizer = EqualizerSettings(enabled = preferences.equalizer.enabled)
                onChange()
                chips.forEach { it.isSelected = false }
                showAll()
            }
            showAll()
        }

        private fun dbFrom(value: Float) = EqualizerSettings.MIN_DB + (EqualizerSettings.MAX_DB - EqualizerSettings.MIN_DB) * value

        private fun positionOf(db: Float) = (db - EqualizerSettings.MIN_DB) / (EqualizerSettings.MAX_DB - EqualizerSettings.MIN_DB)

        /** Moving anything turns the equalizer on: otherwise the change would do nothing. */
        private fun changed(settings: EqualizerSettings) {
            enabled.isChecked = true
            preferences.equalizer = settings.copy(enabled = true)
            onChange()
        }

        private fun showAll() {
            val settings = preferences.equalizer
            bass.value = preferences.equalizerBass
            preamp.value = positionOf(settings.preampDb)
            sliders.forEachIndexed { band, slider ->
                slider.value = positionOf(settings.bandsDb[band])
                levels[band].text = "%+.0f".format(settings.bandsDb[band])
            }
        }

        private fun bands() {
            val row = dialog.findViewById<LinearLayout>(R.id.eqBands)
            val frequencies = engine?.equalizerBandFrequencies().orEmpty()
            for (band in 0 until EqualizerSettings.BAND_COUNT) {
                val name = frequencies.getOrNull(band)?.let(::frequencyLabel) ?: "${band + 1}"
                val column = LinearLayout(activity).apply {
                    orientation = LinearLayout.VERTICAL
                    gravity = Gravity.CENTER_HORIZONTAL
                }
                val level = caption()
                val slider = BandSlider(activity).apply {
                    contentDescription = name
                    spoken = { "%+.1f dB".format(dbFrom(value)) }
                    onChange = { position ->
                        val current = preferences.equalizer
                        val moved = current.bandsDb.toMutableList().also { it[band] = dbFrom(position) }
                        changed(current.copy(bandsDb = moved))
                        level.text = "%+.0f".format(moved[band])
                        chips.forEach { it.isSelected = false }
                    }
                }
                sliders += slider
                levels += level
                column.addView(level)
                column.addView(slider, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
                column.addView(caption().apply { text = name })
                row.addView(column, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f))
            }
        }

        private fun caption() = TextView(activity).apply {
            textSize = 11f
            gravity = Gravity.CENTER
            maxLines = 1
            setTextColor(activity.themeColor(R.attr.inkMutedColor))
        }

        private fun frequencyLabel(hz: Float): String =
            if (hz >= 1000) "${(hz / 1000).roundToInt()}k" else hz.roundToInt().toString()

        private fun presets() {
            val row = dialog.findViewById<LinearLayout>(R.id.eqPresets)
            val current = engine ?: return
            current.equalizerPresets().forEachIndexed { index, name ->
                val chip = TextView(activity).apply {
                    text = name
                    setBackgroundResource(R.drawable.bg_chip)
                    setTextColor(activity.themeColor(R.attr.inkColor))
                    gravity = Gravity.CENTER
                    minHeight = (CHIP_DP * density).toInt()
                    setPadding((16 * density).toInt(), 0, (16 * density).toInt(), 0)
                    isClickable = true
                    isFocusable = true
                    setOnClickListener {
                        preferences.equalizerBass = 0f
                        changed(current.equalizerPreset(index))
                        chips.forEach { it.isSelected = it === this }
                        showAll()
                    }
                }
                chips += chip
                row.addView(
                    chip,
                    LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                        marginEnd = (8 * density).toInt()
                    },
                )
            }
        }
    }

    private const val CHIP_DP = 48
}
