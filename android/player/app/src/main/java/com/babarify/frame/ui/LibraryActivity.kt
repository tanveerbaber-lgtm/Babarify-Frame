package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.DocumentsContract
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.EditText
import android.widget.ListView
import android.widget.TextView
import android.widget.Toast
import com.babarify.frame.R
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.core.SortOrder
import com.babarify.frame.data.HistoryStore
import com.babarify.frame.data.LibraryFolder
import com.babarify.frame.data.LibraryScanner
import com.babarify.frame.data.LibraryStore
import com.babarify.frame.data.MediaEntry
import com.babarify.frame.engine.PlaybackSession

/** Only folders the user picks are read. Android grants exactly those; no storage permission is used. */
class LibraryActivity : Activity() {
    private lateinit var store: LibraryStore
    private lateinit var history: HistoryStore
    private lateinit var scanner: LibraryScanner
    private lateinit var session: PlaybackSession
    private lateinit var adapter: MediaRowAdapter
    private lateinit var nowPlaying: NowPlayingBar
    private lateinit var status: TextView
    private lateinit var search: EditText
    private var entries: List<MediaEntry> = emptyList()

    /** For tests. */
    val shownEntries: List<MediaEntry> get() = entries
    val scanning: Boolean get() = scanner.busy
    fun addFolder(uri: Uri) = addGrantedFolder(uri)
    fun setSearch(text: String) = search.setText(text)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_library)
        applySystemBarPadding(findViewById(R.id.libraryRoot))
        store = LibraryStore(this)
        history = HistoryStore(this)
        session = PlaybackSession.get(this)
        scanner = LibraryScanner(this, store, isPlaybackActive = { session.isPlaying }, onChanged = ::refresh)
        adapter = MediaRowAdapter(this)
        status = findViewById(R.id.libraryStatus)
        search = findViewById(R.id.searchBox)
        val list = findViewById<ListView>(R.id.mediaList)
        list.adapter = adapter
        list.setOnItemClickListener { _, _, position, _ ->
            startActivity(Intent(this, PlayerActivity::class.java).setData(Uri.parse(entries[position].uri)))
        }
        list.setOnItemLongClickListener { _, _, position, _ ->
            choosePlaylist(entries[position])
            true
        }
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) = refresh()
        })
        findViewById<View>(R.id.addFolderButton).setOnClickListener { pickFolder() }
        findViewById<View>(R.id.foldersButton).setOnClickListener { showFolders() }
        findViewById<View>(R.id.sortButton).setOnClickListener { chooseSort() }
        BottomNav.attach(this, findViewById(R.id.bottomNav))
        nowPlaying = NowPlayingBar(this)
    }

    override fun onStart() {
        super.onStart()
        refresh()
        scanner.scan()
        nowPlaying.start()
    }

    override fun onStop() {
        nowPlaying.stop()
        super.onStop()
    }

    override fun onDestroy() {
        scanner.shutdown()
        store.close()
        history.close()
        super.onDestroy()
    }

    private fun refresh() {
        if (isDestroyed) return
        val sort = session.preferences.librarySort
        val recent = if (sort == SortOrder.RECENTLY_PLAYED) history.lastPlayed() else emptyMap()
        entries = store.media(search.text.toString(), sort, recent)
        adapter.rows = entries.map {
            MediaRow(it.name, detail(it), it.thumbnail, placeholder = if (it.isVideo) R.drawable.ic_movie else R.drawable.ic_audio)
        }
        val message = when {
            entries.isNotEmpty() -> null
            scanner.busy -> getString(R.string.scanning)
            search.text.isNotBlank() -> getString(R.string.no_results)
            else -> getString(R.string.library_empty)
        }
        status.text = message
        status.visibility = if (message == null) View.GONE else View.VISIBLE
    }

    private fun detail(entry: MediaEntry): String {
        val size = getString(R.string.size_mb, entry.size / 1_000_000.0)
        val duration = entry.durationMs ?: return size
        return getString(R.string.file_details, PlaybackRules.formatTime(duration), size)
    }

    private fun pickFolder() {
        val pick = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_FOLDER)
    }

    @Deprecated("The activity result API would add androidx.activity for one call.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (requestCode != REQUEST_FOLDER || resultCode != RESULT_OK || uri == null) return
        try {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: SecurityException) {
            // Lent for now only: the folder works until Android takes the access back.
        }
        addGrantedFolder(uri)
    }

    private fun addGrantedFolder(uri: Uri) {
        val id = store.addFolder(uri.toString(), folderName(uri))
        store.folders().firstOrNull { it.id == id }?.let { scanner.scan(listOf(it)) }
        refresh()
    }

    private fun folderName(tree: Uri): String {
        val document = DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
        return session.displayName(document) ?: DocumentsContract.getTreeDocumentId(tree).substringAfterLast(':')
    }

    private fun showFolders() {
        val folders = store.folders()
        val builder = AlertDialog.Builder(this).setTitle(R.string.folders)
            .setPositiveButton(R.string.rescan) { _, _ -> scanner.scan() }
            .setNegativeButton(android.R.string.cancel, null)
        if (folders.isEmpty()) {
            builder.setMessage(R.string.no_folders)
        } else {
            builder.setItems(folders.map { it.name }.toTypedArray()) { _, which -> confirmRemoveFolder(folders[which]) }
        }
        builder.show()
    }

    private fun confirmRemoveFolder(folder: LibraryFolder) {
        AlertDialog.Builder(this)
            .setTitle(folder.name)
            .setMessage(R.string.remove_folder_question)
            .setPositiveButton(R.string.remove) { _, _ ->
                store.removeFolder(folder.id)
                releaseFileAccess(this, folder.uri)
                refresh()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun chooseSort() {
        val orders = SortOrder.entries
        val labels = listOf(
            R.string.sort_name,
            R.string.sort_date_added,
            R.string.sort_recently_played,
            R.string.sort_duration,
            R.string.sort_size,
        ).map(::getString)
        AlertDialog.Builder(this)
            .setTitle(R.string.sort)
            .setSingleChoiceItems(labels.toTypedArray(), orders.indexOf(session.preferences.librarySort)) { dialog, which ->
                session.preferences.librarySort = orders[which]
                refresh()
                dialog.dismiss()
            }
            .show()
    }

    private fun choosePlaylist(entry: MediaEntry) {
        val playlists = store.playlists()
        val labels = playlists.map { it.name } + getString(R.string.new_playlist)
        AlertDialog.Builder(this)
            .setTitle(R.string.add_to_playlist)
            .setItems(labels.toTypedArray()) { _, which ->
                val playlist = playlists.getOrNull(which)
                if (playlist == null) {
                    askPlaylistName(this, null) { name ->
                        store.addToPlaylist(store.createPlaylist(name), entry.uri, entry.name)
                        Toast.makeText(this, getString(R.string.added_to_playlist, name), Toast.LENGTH_SHORT).show()
                    }
                } else {
                    store.addToPlaylist(playlist.id, entry.uri, entry.name)
                    Toast.makeText(this, getString(R.string.added_to_playlist, playlist.name), Toast.LENGTH_SHORT).show()
                }
            }
            .show()
    }

    private companion object {
        const val REQUEST_FOLDER = 3
    }
}

fun askPlaylistName(activity: Activity, current: String?, onName: (String) -> Unit) {
    val input = EditText(activity).apply {
        hint = activity.getString(R.string.playlist_name)
        setText(current.orEmpty())
        setSingleLine()
    }
    AlertDialog.Builder(activity)
        .setTitle(if (current == null) R.string.new_playlist else R.string.rename)
        .setView(input)
        .setPositiveButton(android.R.string.ok) { _, _ ->
            input.text.toString().trim().takeIf { it.isNotEmpty() }?.let(onName)
        }
        .setNegativeButton(android.R.string.cancel, null)
        .show()
}
