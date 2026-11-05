package com.babarify.frame.ui

import android.app.Activity
import android.content.Intent
import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import com.babarify.frame.R

/** The tabs along the bottom of the main screens. Home stays underneath, so Back always leads there. */
object BottomNav {
    private val TABS = listOf(
        R.id.navHome to HomeActivity::class.java,
        R.id.navMusic to MusicActivity::class.java,
        R.id.navLibrary to LibraryActivity::class.java,
        R.id.navPlaylists to PlaylistsActivity::class.java,
        R.id.navSettings to SettingsActivity::class.java,
    )

    fun attach(activity: Activity, container: ViewGroup) {
        LayoutInflater.from(activity).inflate(R.layout.bottom_nav, container, true)
        for ((id, target) in TABS) {
            val tab = container.findViewById<LinearLayout>(id)
            val current = target == activity.javaClass
            val colour = if (current) activity.themeColor(R.attr.accent2Color) else activity.themeColor(R.attr.inkMutedColor)
            (tab.getChildAt(0) as ImageView).imageTintList = android.content.res.ColorStateList.valueOf(colour)
            (tab.getChildAt(1) as TextView).setTextColor(colour)
            tab.isSelected = current
            tab.setOnClickListener { if (!current) open(activity, target) }
        }
    }

    private fun open(activity: Activity, target: Class<out Activity>) {
        if (target != HomeActivity::class.java) {
            activity.startActivity(Intent(activity, target).addFlags(Intent.FLAG_ACTIVITY_NO_ANIMATION))
        }
        if (activity !is HomeActivity) activity.finish()
    }
}
