package com.babarify.frame.data

import android.content.Context

class Preferences(context: Context) {
    private val store = context.applicationContext.getSharedPreferences("preferences", Context.MODE_PRIVATE)

    var hardwareDecoding: Boolean
        get() = store.getBoolean("hardware_decoding", true)
        set(value) = store.edit().putBoolean("hardware_decoding", value).apply()

    var resumePlayback: Boolean
        get() = store.getBoolean("resume_playback", true)
        set(value) = store.edit().putBoolean("resume_playback", value).apply()
}
