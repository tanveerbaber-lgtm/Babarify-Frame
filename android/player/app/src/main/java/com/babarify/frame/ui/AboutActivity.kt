package com.babarify.frame.ui

import android.app.Activity
import android.os.Bundle
import android.widget.TextView
import com.babarify.frame.R

class AboutActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_about)
        applySystemBarPadding(findViewById(R.id.aboutRoot))
        val version = packageManager.getPackageInfo(packageName, 0).versionName
        findViewById<TextView>(R.id.aboutTitle).text = getString(R.string.about_title, version)
        findViewById<TextView>(R.id.aboutText).text = LICENCE_FILES.joinToString("\n\n") { name ->
            assets.open("licenses/$name").bufferedReader().use { it.readText() }
        }
    }

    private companion object {
        val LICENCE_FILES = listOf("THIRD_PARTY_NOTICES.txt", "GPL-3.0.txt", "LGPL-2.1.txt", "Apache-2.0.txt")
    }
}
