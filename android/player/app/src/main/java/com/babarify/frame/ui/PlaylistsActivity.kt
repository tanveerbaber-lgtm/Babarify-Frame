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
import com.babarify.frame.data.LibraryStore
import com.babarify.frame.data.MediaEntry
import com.babarify.frame.data.Playlist
import com.babarify.frame.data.PlaylistItem
import com.babarify.frame.engine.PlaybackSession

class PlaylistsActivity : Activity() {
    private lateinit var store: LibraryStore
    private lateinit var adapter: MediaRowAdapter
    private lateinit var empty: TextView
    private var playlists: List<Playlist> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_playlists)
        applySystemBarPadding(findViewById(R.id.playlistsRoot))
        store = LibraryStore(this)
        adapter = MediaRowAdapter(this)
        empty = findViewById(R.id.playlistsEmpty)
        empty.setText(R.string.no_playlists)
        BottomNav.attach(this, findViewById(R.id.bottomNav))
        val list = findViewById<ListView>(R.id.playlistsList)
        list.adapter = adapter
        list.setOnItemClickListener { _, _, position, _ ->
            openPlaylist(playlists[position].id, playlists[position].name)
        }
        list.setOnItemLongClickListener { _, _, position, _ ->
            manage(playlists[position])
            true
        }
        findViewById<Button>(R.id.playlistsAction).apply {
            setText(R.string.new_playlist)
            setCompoundDrawablesRelativeWithIntrinsicBounds(R.drawable.ic_add, 0, 0, 0)
            setOnClickListener {
                askPlaylistName(this@PlaylistsActivity, null) { name ->
                    openPlaylist(store.createPlaylist(name), name) // Straight to adding media.
                }
            }
        }
    }

    override fun onStart() {
        super.onStart()
        refresh()
    }

    override fun onDestroy() {
        store.close()
        super.onDestroy()
    }

    private fun refresh() {
        playlists = store.playlists()
        adapter.rows = playlists.map {
            MediaRow(it.name, getString(R.string.playlist_count, it.itemCount), placeholder = R.drawable.ic_playlist)
        }
        empty.visibility = if (playlists.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun openPlaylist(id: Long, name: String) {
        startActivity(
            Intent(this, PlaylistActivity::class.java)
                .putExtra(PlaylistActivity.EXTRA_ID, id)
                .putExtra(PlaylistActivity.EXTRA_NAME, name),
        )
    }

    private fun manage(playlist: Playlist) {
        val actions = listOf(getString(R.string.rename), getString(R.string.delete))
        AlertDialog.Builder(this)
            .setTitle(playlist.name)
            .setItems(actions.toTypedArray()) { _, which ->
                if (which == 0) {
                    askPlaylistName(this, playlist.name) { name ->
                        store.renamePlaylist(playlist.id, name)
                        refresh()
                    }
                } else {
                    AlertDialog.Builder(this)
                        .setMessage(R.string.delete_playlist_question)
                        .setPositiveButton(R.string.delete) { _, _ ->
                            store.deletePlaylist(playlist.id)
                            refresh()
                        }
                        .setNegativeButton(android.R.string.cancel, null)
                        .show()
                }
            }
            .show()
    }
}

/** One playlist: play it from any file, reorder it, remove files from it. */
class PlaylistActivity : Activity() {
    private lateinit var store: LibraryStore
    private lateinit var adapter: MediaRowAdapter
    private lateinit var empty: TextView
    private var playlistId = 0L
    private var items: List<PlaylistItem> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_playlists)
        applySystemBarPadding(findViewById(R.id.playlistsRoot))
        store = LibraryStore(this)
        adapter = MediaRowAdapter(this)
        playlistId = intent.getLongExtra(EXTRA_ID, 0)
        findViewById<TextView>(R.id.playlistsTitle).text = intent.getStringExtra(EXTRA_NAME).orEmpty()
        empty = findViewById(R.id.playlistsEmpty)
        empty.setText(R.string.playlist_empty)
        findViewById<View>(R.id.bottomNav).visibility = View.GONE
        val list = findViewById<ListView>(R.id.playlistsList)
        list.adapter = adapter
        list.setOnItemClickListener { _, _, position, _ -> play(position) }
        list.setOnItemLongClickListener { _, _, position, _ ->
            manage(items[position])
            true
        }
        findViewById<Button>(R.id.playlistsAction).apply {
            setText(R.string.play_all)
            setCompoundDrawablesRelativeWithIntrinsicBounds(R.drawable.ic_play, 0, 0, 0)
            setOnClickListener { if (items.isNotEmpty()) play(0) }
        }
        findViewById<Button>(R.id.playlistsAdd).apply {
            visibility = View.VISIBLE
            setOnClickListener { chooseWhereToAddFrom() }
        }
    }

    override fun onStart() {
        super.onStart()
        refresh()
    }

    override fun onDestroy() {
        store.close()
        super.onDestroy()
    }

    private fun refresh() {
        items = store.playlistItems(playlistId)
        adapter.rows = items.map { MediaRow(it.title, "", placeholder = placeholderFor(it.title)) }
        empty.visibility = if (items.isEmpty()) View.VISIBLE else View.GONE
    }

    /** The library if it has anything, or files from anywhere through the system's picker. */
    private fun chooseWhereToAddFrom() {
        val entries = store.media()
        if (entries.isEmpty()) {
            pickFiles()
            return
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.add_media)
            .setItems(arrayOf(getString(R.string.add_from_library), getString(R.string.add_from_files))) { _, which ->
                if (which == 0) chooseFromLibrary(entries) else pickFiles()
            }
            .show()
    }

    private fun chooseFromLibrary(entries: List<MediaEntry>) {
        val chosen = BooleanArray(entries.size)
        AlertDialog.Builder(this)
            .setTitle(R.string.add_from_library)
            .setMultiChoiceItems(entries.map { it.name }.toTypedArray(), chosen) { _, which, checked ->
                chosen[which] = checked
            }
            .setPositiveButton(R.string.add_media) { _, _ ->
                entries.filterIndexed { index, _ -> chosen[index] }.forEach { store.addToPlaylist(playlistId, it.uri, it.name) }
                refresh()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun pickFiles() {
        val pick = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("video/*", "audio/*"))
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        }
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_FILES)
    }

    @Deprecated("The activity result API would add androidx.activity for one call.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_FILES || resultCode != RESULT_OK || data == null) return
        val clip = data.clipData
        val picked = if (clip != null) List(clip.itemCount) { clip.getItemAt(it).uri } else listOfNotNull(data.data)
        addFiles(picked)
    }

    /** Keeps lasting access to exactly these files, so the playlist still works next time. */
    fun addFiles(uris: List<Uri>) {
        val session = PlaybackSession.get(this)
        for (uri in uris) {
            try {
                contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } catch (_: SecurityException) {
                // Lent for now only: it plays until Android takes the access back.
            }
            store.addToPlaylist(playlistId, uri.toString(), session.displayName(uri) ?: getString(R.string.untitled))
        }
        refresh()
    }

    /** For tests. */
    val shownItems: List<PlaylistItem> get() = items

    private fun play(index: Int) {
        startActivity(
            Intent(this, PlayerActivity::class.java)
                .setData(Uri.parse(items[index].uri))
                .putStringArrayListExtra(PlayerActivity.EXTRA_QUEUE_URIS, ArrayList(items.map { it.uri }))
                .putStringArrayListExtra(PlayerActivity.EXTRA_QUEUE_TITLES, ArrayList(items.map { it.title }))
                .putExtra(PlayerActivity.EXTRA_QUEUE_INDEX, index),
        )
    }

    private fun manage(item: PlaylistItem) {
        val actions = listOf(getString(R.string.move_up), getString(R.string.move_down), getString(R.string.remove))
        AlertDialog.Builder(this)
            .setTitle(item.title)
            .setItems(actions.toTypedArray()) { _, which ->
                when (which) {
                    0 -> store.moveInPlaylist(item, -1)
                    1 -> store.moveInPlaylist(item, 1)
                    else -> store.removePlaylistItem(item)
                }
                refresh()
            }
            .show()
    }

    companion object {
        const val EXTRA_ID = "com.babarify.frame.PLAYLIST_ID"
        const val EXTRA_NAME = "com.babarify.frame.PLAYLIST_NAME"
        private const val REQUEST_FILES = 4
    }
}
