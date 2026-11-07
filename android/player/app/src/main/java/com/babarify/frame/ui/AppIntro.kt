package com.babarify.frame.ui

import android.animation.ValueAnimator
import android.app.Activity
import android.graphics.LinearGradient
import android.graphics.Outline
import android.graphics.Shader
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.ViewOutlineProvider
import android.view.animation.DecelerateInterpolator
import android.view.animation.OvershootInterpolator
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import com.babarify.frame.R

/** The name in the colours of the logo and the main button, in every colour theme. */
fun TextView.brandColours() {
    addOnLayoutChangeListener { view, _, _, _, _, _, _, _, _ ->
        val text = view as TextView
        val width = text.paint.measureText(text.text.toString()).coerceAtLeast(1f)
        val start = context.themeColor(R.attr.accentColor)
        val end = context.themeColor(R.attr.accent2Color)
        text.paint.shader = LinearGradient(0f, 0f, width, 0f, start, end, Shader.TileMode.CLAMP)
    }
}

/**
 * The icon and name, animated in 3D over the home screen when the app starts fresh: the icon turns in and
 * catches the light, then the name tips up into place. It plays once per start of the app, can be skipped
 * with a tap, and is left out when the phone is set to remove animations. Android's own start-up screen is
 * left plain (see the theme), so this is the only intro.
 */
object AppIntro {
    const val TAG = "app_intro"

    private const val BACKGROUND = 0xFF070B15.toInt() // the brand's dark blue, as on the start-up screen
    private const val BLUE = 0xFF3B82F6.toInt()
    private const val CYAN = 0xFF22D3EE.toInt()
    private const val TITLE_COLOUR = 0xFFE6EDF7.toInt()
    private const val TAGLINE_COLOUR = 0xFFA3B1C9.toInt()

    private const val ICON_DP = 112
    private const val GAP_DP = 22 // the same between the icon and the name, and the name and the tagline
    private const val CAMERA = 9000f

    private const val ICON_TURN_MS = 750L
    private const val SHINE_START_MS = 650L
    private const val SHINE_MS = 650L
    private const val TITLE_START_MS = 550L
    private const val TITLE_MS = 600L
    private const val TAGLINE_START_MS = 950L
    private const val TAGLINE_MS = 450L
    private const val LEAVE_START_MS = 2100L
    private const val LEAVE_MS = 350L

    private var played = false

    /** For tests: how many times it has played. */
    var plays = 0
        private set

    /** For tests: lets the next home screen play it again. */
    fun forget() {
        played = false
    }

    fun playOnce(activity: Activity) {
        if (played) return
        played = true
        if (!ValueAnimator.areAnimatorsEnabled()) return
        val density = activity.resources.displayMetrics.density
        fun dp(value: Int) = (value * density).toInt()

        val overlay = FrameLayout(activity).apply {
            tag = TAG
            setBackgroundColor(BACKGROUND)
            isClickable = true
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
            setOnClickListener { leave(this, 0) }
        }
        val glow = View(activity).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                gradientType = GradientDrawable.RADIAL_GRADIENT
                gradientRadius = dp(150).toFloat()
                colors = intArrayOf((CYAN and 0x00FFFFFF) or 0x55000000, 0x00000000)
            }
            alpha = 0f
        }
        overlay.addView(glow, FrameLayout.LayoutParams(dp(300), dp(300), Gravity.CENTER))

        val stack = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(24), 0, dp(24), 0)
        }
        val corner = ICON_DP * 0.22f * density
        val roundCorners = object : ViewOutlineProvider() {
            override fun getOutline(view: View, outline: Outline) =
                outline.setRoundRect(0, 0, view.width, view.height, corner)
        }
        val iconFrame = FrameLayout(activity).apply {
            outlineProvider = roundCorners
            clipToOutline = true
            elevation = dp(18).toFloat()
            cameraDistance = CAMERA * density
            alpha = 0f
            rotationY = -110f
            scaleX = 0.7f
            scaleY = 0.7f
        }
        iconFrame.addView(
            ImageView(activity).apply {
                setImageResource(R.mipmap.ic_launcher)
                scaleType = ImageView.ScaleType.CENTER_CROP
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            },
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )
        val shine = View(activity).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                intArrayOf(0x00FFFFFF, 0x66FFFFFF, 0x00FFFFFF),
            )
            rotation = 20f
            translationX = -dp(ICON_DP) * 1.4f
        }
        iconFrame.addView(shine, FrameLayout.LayoutParams(dp(ICON_DP / 2), dp(ICON_DP * 2), Gravity.CENTER))
        stack.addView(iconFrame, LinearLayout.LayoutParams(dp(ICON_DP), dp(ICON_DP)))

        val title = TextView(activity).apply {
            setText(R.string.app_name)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 28f)
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(TITLE_COLOUR)
            gravity = Gravity.CENTER
            maxLines = 2
            alpha = 0f
            cameraDistance = CAMERA * density
            rotationX = 80f
            addOnLayoutChangeListener { view, _, top, _, bottom, _, _, _, _ ->
                view.pivotY = (bottom - top).toFloat()
                val text = view as TextView
                val lineWidth = text.paint.measureText(text.text.toString()).coerceAtMost(text.width.toFloat())
                val left = (text.width - lineWidth) / 2
                text.paint.shader = LinearGradient(left, 0f, left + lineWidth, 0f, BLUE, CYAN, Shader.TileMode.CLAMP)
            }
        }
        stack.addView(
            title,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(GAP_DP)
            },
        )
        val tagline = TextView(activity).apply {
            setText(R.string.tagline)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            setTextColor(TAGLINE_COLOUR)
            gravity = Gravity.CENTER
            alpha = 0f
            translationY = dp(10).toFloat()
        }
        stack.addView(
            tagline,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(GAP_DP)
            },
        )
        overlay.addView(
            stack,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER),
        )
        plays++
        (activity.window.decorView as ViewGroup).addView(
            overlay,
            ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT),
        )
        // The glow stays centred on the icon, whatever the screen's height.
        stack.addOnLayoutChangeListener { _, _, top, _, _, _, _, _, _ ->
            glow.translationY = top + iconFrame.top + iconFrame.height / 2f - overlay.height / 2f
        }

        iconFrame.animate().alpha(1f).rotationY(0f).scaleX(1f).scaleY(1f)
            .setDuration(ICON_TURN_MS).setInterpolator(OvershootInterpolator(1.2f))
        glow.animate().alpha(1f).setStartDelay(ICON_TURN_MS / 2).setDuration(ICON_TURN_MS)
        shine.animate().translationX(dp(ICON_DP) * 1.4f)
            .setStartDelay(SHINE_START_MS).setDuration(SHINE_MS).setInterpolator(DecelerateInterpolator())
        title.animate().alpha(1f).rotationX(0f)
            .setStartDelay(TITLE_START_MS).setDuration(TITLE_MS).setInterpolator(DecelerateInterpolator(1.6f))
        tagline.animate().alpha(1f).translationY(0f)
            .setStartDelay(TAGLINE_START_MS).setDuration(TAGLINE_MS).setInterpolator(DecelerateInterpolator())
        leave(overlay, LEAVE_START_MS)
    }

    private fun leave(overlay: View, delay: Long) {
        overlay.animate().cancel()
        overlay.animate().alpha(0f).scaleX(1.04f).scaleY(1.04f).setStartDelay(delay).setDuration(LEAVE_MS)
            .withEndAction { (overlay.parent as? ViewGroup)?.removeView(overlay) }
    }
}
