package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.ListView
import android.widget.TextView
import com.babarify.frame.R
import com.babarify.frame.data.HistoryEntry
import com.babarify.frame.data.HistoryStore
import com.babarify.frame.data.Preferences

class HomeActivity : Activity() {
    private lateinit var history: HistoryStore
    private lateinit var preferences: Preferences
    private lateinit var recentList: ListView
    private lateinit var emptyLabel: TextView
    private var entries: List<HistoryEntry> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)
        applySystemBarPadding(findViewById(R.id.homeRoot))
        history = HistoryStore(this)
        preferences = Preferences(this)
        recentList = findViewById(R.id.recentList)
        emptyLabel = findViewById(R.id.emptyLabel)

        findViewById<Button>(R.id.openButton).setOnClickListener { openPicker() }
        findViewById<Button>(R.id.settingsButton).setOnClickListener { showSettings() }
        findViewById<Button>(R.id.aboutButton).setOnClickListener {
            startActivity(Intent(this, AboutActivity::class.java))
        }
        recentList.setOnItemClickListener { _, _, position, _ -> play(Uri.parse(entries[position].uri)) }
        recentList.setOnItemLongClickListener { _, _, position, _ ->
            forget(entries[position].uri)
            true
        }
    }

    override fun onStart() {
        super.onStart()
        refreshRecent()
    }

    override fun onDestroy() {
        history.close()
        super.onDestroy()
    }

    private fun refreshRecent() {
        entries = history.recent()
        recentList.adapter = ArrayAdapter(this, R.layout.item_recent, entries.map { it.title })
        emptyLabel.visibility = if (entries.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun openPicker() {
        val pick = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("video/*", "audio/*"))
        }
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_OPEN)
    }

    @Deprecated("The activity result API would add androidx.activity for one call.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (requestCode != REQUEST_OPEN || resultCode != RESULT_OK || uri == null) return
        // Keeps access to this one file across restarts; nothing else becomes readable.
        try {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: SecurityException) {
            // Some providers lend a file only for now: it still plays, but may not reopen later.
        }
        play(uri)
    }

    private fun play(uri: Uri) {
        startActivity(Intent(this, PlayerActivity::class.java).setData(uri))
    }

    private fun forget(uri: String) {
        AlertDialog.Builder(this)
            .setMessage(R.string.forget_question)
            .setPositiveButton(R.string.remove) { _, _ ->
                history.remove(uri)
                releaseAccess(uri)
                refreshRecent()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun releaseAccess(uri: String) {
        try {
            contentResolver.releasePersistableUriPermission(Uri.parse(uri), Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: SecurityException) {
            // There was no lasting permission to give back.
        }
    }

    private fun showSettings() {
        val view = layoutInflater.inflate(R.layout.dialog_settings, null)
        val hardware = view.findViewById<CheckBox>(R.id.hardwareCheck)
        val resume = view.findViewById<CheckBox>(R.id.resumeCheck)
        hardware.isChecked = preferences.hardwareDecoding
        resume.isChecked = preferences.resumePlayback
        hardware.setOnCheckedChangeListener { _, on -> preferences.hardwareDecoding = on }
        resume.setOnCheckedChangeListener { _, on -> preferences.resumePlayback = on }
        view.findViewById<Button>(R.id.clearButton).setOnClickListener {
            history.recent(Int.MAX_VALUE).forEach { releaseAccess(it.uri) }
            history.clear()
            refreshRecent()
        }
        AlertDialog.Builder(this).setTitle(R.string.settings).setView(view)
            .setPositiveButton(android.R.string.ok, null).show()
    }

    private companion object {
        const val REQUEST_OPEN = 1
    }
}
