package com.babarify.frame.ui

import android.animation.ValueAnimator
import android.app.Activity
import android.graphics.LinearGradient
import android.graphics.Shader
import android.graphics.drawable.GradientDrawable
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.animation.DecelerateInterpolator
import android.view.animation.OvershootInterpolator
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import com.babarify.frame.R

/**
 * The icon and name, animated over the home screen when the app starts fresh. It plays once per start of
 * the app, can be skipped with a tap, and is left out when the phone is set to remove animations.
 */
object AppIntro {
    const val TAG = "app_intro"
    private const val ICON_MS = 550L
    private const val GLOW_START_MS = 200L
    private const val GLOW_MS = 800L
    private const val TITLE_START_MS = 350L
    private const val TITLE_MS = 450L
    private const val TAGLINE_START_MS = 650L
    private const val TAGLINE_MS = 350L
    private const val LEAVE_START_MS = 1500L
    private const val LEAVE_MS = 300L

    private var played = false

    /** For tests: lets the next home screen play it again. */
    fun forget() {
        played = false
    }

    fun playOnce(activity: Activity) {
        if (played) return
        played = true
        if (!ValueAnimator.areAnimatorsEnabled()) return
        val root = activity.window.decorView as ViewGroup
        val overlay = FrameLayout(activity).apply {
            tag = TAG
            setBackgroundColor(activity.themeColor(R.attr.bgColor))
            isClickable = true
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
            setOnClickListener { leave(this, 0) }
        }
        fun dp(value: Int) = (value * activity.resources.displayMetrics.density).toInt()

        val stack = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(24), 0, dp(24), 0)
        }
        val iconArea = FrameLayout(activity)
        val glow = View(activity).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                gradientType = GradientDrawable.RADIAL_GRADIENT
                gradientRadius = dp(110).toFloat()
                colors = intArrayOf(activity.themeColor(R.attr.accent2Color), 0x00000000)
            }
            alpha = 0f
        }
        iconArea.addView(glow, FrameLayout.LayoutParams(dp(220), dp(220), Gravity.CENTER))
        val icon = ImageView(activity).apply {
            setImageResource(R.mipmap.ic_launcher)
            alpha = 0f
            scaleX = 0.6f
            scaleY = 0.6f
        }
        iconArea.addView(icon, FrameLayout.LayoutParams(dp(120), dp(120), Gravity.CENTER))
        stack.addView(iconArea, LinearLayout.LayoutParams(dp(220), dp(220)))

        val title = TextView(activity).apply {
            setText(R.string.app_name)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 28f)
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            gravity = Gravity.CENTER
            maxLines = 2
            alpha = 0f
            translationY = dp(24).toFloat()
            setTextColor(activity.themeColor(R.attr.inkColor))
            addOnLayoutChangeListener { view, left, _, right, _, _, _, _, _ ->
                val start = activity.themeColor(R.attr.accentColor)
                val end = activity.themeColor(R.attr.accent2Color)
                (view as TextView).paint.shader =
                    LinearGradient(0f, 0f, (right - left).toFloat(), 0f, start, end, Shader.TileMode.CLAMP)
            }
        }
        stack.addView(title, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        val tagline = TextView(activity).apply {
            setText(R.string.tagline)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            setTextColor(activity.themeColor(R.attr.inkMutedColor))
            gravity = Gravity.CENTER
            alpha = 0f
        }
        stack.addView(
            tagline,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(8)
            },
        )
        overlay.addView(
            stack,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER),
        )
        root.addView(overlay, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

        icon.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(ICON_MS).setInterpolator(OvershootInterpolator(1.6f))
        glow.scaleX = 0.5f
        glow.scaleY = 0.5f
        glow.animate().alpha(0.55f).scaleX(1f).scaleY(1f).setStartDelay(GLOW_START_MS).setDuration(GLOW_MS)
            .setInterpolator(DecelerateInterpolator())
        title.animate().alpha(1f).translationY(0f).setStartDelay(TITLE_START_MS).setDuration(TITLE_MS)
            .setInterpolator(DecelerateInterpolator())
        tagline.animate().alpha(1f).setStartDelay(TAGLINE_START_MS).setDuration(TAGLINE_MS)
        leave(overlay, LEAVE_START_MS)
    }

    private fun leave(overlay: View, delay: Long) {
        overlay.animate().cancel()
        overlay.animate().alpha(0f).setStartDelay(delay).setDuration(LEAVE_MS).withEndAction {
            (overlay.parent as? ViewGroup)?.removeView(overlay)
        }
    }
}
