package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.ListView
import android.widget.TextView
import com.babarify.frame.R
import com.babarify.frame.core.MusicRules
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.data.HistoryEntry
import com.babarify.frame.data.HistoryStore
import com.babarify.frame.data.LibraryStore

class HomeActivity : Activity() {
    private lateinit var history: HistoryStore
    private lateinit var library: LibraryStore
    private lateinit var recentList: ListView
    private lateinit var emptyLabel: TextView
    private lateinit var adapter: MediaRowAdapter
    private lateinit var nowPlaying: NowPlayingBar
    private var entries: List<HistoryEntry> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)
        applySystemBarPadding(findViewById(R.id.homeRoot))
        history = HistoryStore(this)
        library = LibraryStore(this)
        recentList = findViewById(R.id.recentList)
        emptyLabel = findViewById(R.id.emptyLabel)
        adapter = MediaRowAdapter(this)
        recentList.adapter = adapter

        findViewById<Button>(R.id.openButton).setOnClickListener { openPicker() }
        BottomNav.attach(this, findViewById(R.id.bottomNav))
        nowPlaying = NowPlayingBar(this)
        recentList.setOnItemClickListener { _, _, position, _ -> play(Uri.parse(entries[position].uri)) }
        recentList.setOnItemLongClickListener { _, _, position, _ ->
            forget(entries[position].uri)
            true
        }
    }

    override fun onStart() {
        super.onStart()
        refreshRecent()
        nowPlaying.start()
    }

    override fun onStop() {
        nowPlaying.stop()
        super.onStop()
    }

    override fun onDestroy() {
        history.close()
        library.close()
        super.onDestroy()
    }

    private fun refreshRecent() {
        entries = history.recent()
        val pictures = library.thumbnailsByFile()
        adapter.rows = entries.map {
            val audio = placeholderFor(it.title) == R.drawable.ic_audio
            MediaRow(
                if (audio) MusicRules.withoutExtension(it.title) else it.title,
                detail(it),
                pictures[it.uri],
                progress(it),
                placeholderFor(it.title),
                artUri = it.uri.takeIf { audio },
            )
        }
        emptyLabel.visibility = if (entries.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun detail(entry: HistoryEntry): String {
        if (entry.finished) return getString(R.string.finished)
        val resume = PlaybackRules.resumePosition(entry.positionMs, entry.durationMs, false)
        return if (resume > 0) getString(R.string.continue_at, PlaybackRules.formatTime(resume)) else ""
    }

    /** Only files you can continue get a bar. */
    private fun progress(entry: HistoryEntry): Float? {
        val duration = entry.durationMs ?: return null
        if (entry.finished || PlaybackRules.resumePosition(entry.positionMs, duration, false) == 0L) return null
        return entry.positionMs.toFloat() / duration
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
                releaseFileAccess(this, uri)
                refreshRecent()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private companion object {
        const val REQUEST_OPEN = 1
    }
}
