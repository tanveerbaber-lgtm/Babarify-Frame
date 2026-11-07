package com.babarify.frame.ui

import android.app.Activity
import android.app.Application
import android.content.Context
import android.os.Bundle
import android.util.TypedValue
import com.babarify.frame.R
import com.babarify.frame.core.ErrorCode
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.engine.PlaybackSession
import com.babarify.frame.engine.SessionListener
import com.babarify.frame.core.VisualStyle
import com.babarify.frame.data.Preferences
import java.util.WeakHashMap

/** A colour from the current theme, for code that draws or tints. */
fun Context.themeColor(attribute: Int): Int {
    val value = TypedValue()
    theme.resolveAttribute(attribute, value, true)
    return value.data
}

/** The animation styles with their names, for the player's menu and Settings. */
val VISUAL_STYLES = listOf(
    VisualStyle.AUTO to R.string.style_auto,
    VisualStyle.MIRROR to R.string.style_mirror,
    VisualStyle.CAPSULES to R.string.style_capsules,
    VisualStyle.WAVES to R.string.style_waves,
    VisualStyle.CIRCLE to R.string.style_circle,
    VisualStyle.LIGHTS to R.string.style_lights,
)

object ColourThemes {
    data class Choice(val key: String, val label: Int, val style: Int?)

    /** The first is the default, drawn from the desktop app's colours. */
    val ALL = listOf(
        Choice("", R.string.theme_ocean, null),
        Choice("sunset", R.string.theme_sunset, R.style.Colours_Sunset),
        Choice("forest", R.string.theme_forest, R.style.Colours_Forest),
        Choice("violet", R.string.theme_violet, R.style.Colours_Violet),
        Choice("amber", R.string.theme_amber, R.style.Colours_Amber),
        Choice("rose", R.string.theme_rose, R.style.Colours_Rose),
        Choice("light", R.string.theme_light, R.style.Colours_Light),
    )

    fun isLight(choice: Choice): Boolean = choice.key == "light"

    fun current(preferences: Preferences): Choice = ALL.firstOrNull { it.key == preferences.colourTheme } ?: ALL.first()
}

/** Lays the chosen colours over every screen as it opens, and refreshes screens left open underneath. */
class BabarifyApp : Application(), Application.ActivityLifecycleCallbacks {
    private val preferences by lazy { Preferences(this) }
    private val applied = WeakHashMap<Activity, String>()

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(this)
        PlaybackSession.get(this).addListener(object : SessionListener {
            override fun onPlaybackStateChanged(state: PlaybackState, error: ErrorCode?) =
                NowPlayingWidget.refresh(this@BabarifyApp)

            override fun onMediaChanged() = NowPlayingWidget.refresh(this@BabarifyApp)
        })
    }

    override fun onActivityPreCreated(activity: Activity, savedInstanceState: Bundle?) {
        val choice = ColourThemes.current(preferences)
        // The player stays dark in a light theme: its controls sit on video.
        val style = choice.style.takeUnless { activity is PlayerActivity && ColourThemes.isLight(choice) }
        style?.let { activity.theme.applyStyle(it, true) }
        applied[activity] = choice.key
    }

    override fun onActivityStarted(activity: Activity) {
        if (activity !is PlayerActivity) PictureBackground.apply(activity)
        // Not the player: it has no colours worth interrupting a video for.
        if (activity !is PlayerActivity && applied[activity] != ColourThemes.current(preferences).key) activity.recreate()
    }

    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit
    override fun onActivityResumed(activity: Activity) = Unit
    override fun onActivityPaused(activity: Activity) = Unit
    override fun onActivityStopped(activity: Activity) = Unit
    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit
    override fun onActivityDestroyed(activity: Activity) = Unit
}
