package com.babarify.frame.ui

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.babarify.frame.engine.PlaybackSession

/** The play and pause button in the small window. */
class PictureToggleReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        PlaybackSession.get(context).togglePlay()
    }
}
