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
import android.widget.Toast
import com.babarify.frame.R
import com.babarify.frame.core.M3u
import com.babarify.frame.core.MusicRules
import com.babarify.frame.core.SongSort
import com.babarify.frame.data.LibraryStore
import com.babarify.frame.data.MediaEntry
import com.babarify.frame.data.MusicLibrary
import com.babarify.frame.data.Playlist
import com.babarify.frame.data.PlaylistItem
import com.babarify.frame.data.SavedTrack
import com.babarify.frame.engine.PlaybackSession

/** Lists that fill themselves in. */
enum class AutoList(val label: Int, val icon: Int, val colour: Int, val lightColour: Int) {
    FAVOURITES(R.string.auto_favourites, R.drawable.ic_heart, 0xFFFB7185.toInt(), 0xFFBE123C.toInt()),
    RECENTLY_PLAYED(R.string.auto_recent, R.drawable.ic_history, 0xFF60A5FA.toInt(), 0xFF1D4ED8.toInt()),
    MOST_PLAYED(R.string.auto_top, R.drawable.ic_trending, 0xFFFBBF24.toInt(), 0xFFB45309.toInt()),
    RECENTLY_ADDED(R.string.auto_new, R.drawable.ic_new, 0xFF34D399.toInt(), 0xFF15803D.toInt()),
}

private const val REQUEST_IMPORT = 5
private const val REQUEST_EXPORT = 6

class PlaylistsActivity : Activity() {
    private var exporting: Playlist? = null

    private lateinit var store: LibraryStore
    private lateinit var adapter: MediaRowAdapter
    private lateinit var nowPlaying: NowPlayingBar
    private lateinit var empty: TextView
    private var playlists: List<Playlist> = emptyList()
    private var automatic: List<AutoList> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_playlists)
        applySystemBarPadding(findViewById(R.id.playlistsRoot))
        store = LibraryStore(this)
        adapter = MediaRowAdapter(this)
        nowPlaying = NowPlayingBar(this)
        empty = findViewById(R.id.playlistsEmpty)
        empty.setText(R.string.no_playlists)
        BottomNav.attach(this, findViewById(R.id.bottomNav))
        findViewById<View>(R.id.playlistsImport).apply {
            visibility = View.VISIBLE
            setOnClickListener { pickPlaylistToImport() }
        }
        val list = findViewById<ListView>(R.id.playlistsList)
        list.adapter = adapter
        list.setOnItemClickListener { _, _, position, _ ->
            val auto = automatic.getOrNull(position)
            if (auto != null) {
                openAutomatic(auto)
            } else {
                val playlist = playlists[position - automatic.size]
                openPlaylist(playlist.id, playlist.name)
            }
        }
        list.setOnItemLongClickListener { _, _, position, _ ->
            playlists.getOrNull(position - automatic.size)?.let(::manage)
            position >= automatic.size
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
        nowPlaying.start()
    }

    override fun onStop() {
        nowPlaying.stop()
        super.onStop()
    }

    override fun onDestroy() {
        store.close()
        super.onDestroy()
    }

    private fun refresh() {
        playlists = store.playlists()
        automatic = AutoList.entries.filter { it != AutoList.RECENTLY_ADDED || MusicLibrary.allowed(this) }
        adapter.rows = automatic.map(::automaticRow) + playlists.map {
            MediaRow(it.name, fileCount(it.itemCount), placeholder = R.drawable.ic_playlist)
        }
        empty.visibility = View.GONE
    }

    private fun fileCount(count: Int): String =
        if (count == 1) getString(R.string.playlist_count_one) else getString(R.string.playlist_count, count)

    private fun automaticRow(list: AutoList): MediaRow {
        val detail = when (list) {
            AutoList.FAVOURITES -> fileCount(store.favourites().size)
            AutoList.RECENTLY_PLAYED -> fileCount(store.recentlyPlayed().size)
            AutoList.MOST_PLAYED -> fileCount(store.mostPlayed().size)
            AutoList.RECENTLY_ADDED -> getString(R.string.auto_new_detail)
        }
        return MediaRow(getString(list.label), detail, placeholder = list.icon, iconColour = if (ColourThemes.isLight(ColourThemes.current(PlaybackSession.get(this).preferences))) list.lightColour else list.colour)
    }

    private fun openAutomatic(list: AutoList) {
        startActivity(
            Intent(this, PlaylistActivity::class.java)
                .putExtra(PlaylistActivity.EXTRA_AUTO, list.name)
                .putExtra(PlaylistActivity.EXTRA_NAME, getString(list.label)),
        )
    }

    private fun openPlaylist(id: Long, name: String) {
        startActivity(
            Intent(this, PlaylistActivity::class.java)
                .putExtra(PlaylistActivity.EXTRA_ID, id)
                .putExtra(PlaylistActivity.EXTRA_NAME, name),
        )
    }

    private fun pickPlaylistToImport() {
        val pick = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
        }
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_IMPORT)
    }

    private fun pickExportFile(playlist: Playlist) {
        exporting = playlist
        val pick = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "audio/x-mpegurl"
            putExtra(Intent.EXTRA_TITLE, "${playlist.name}.m3u")
        }
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_EXPORT)
    }

    @Deprecated("The activity result API would add androidx.activity for one call.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (resultCode != RESULT_OK || uri == null) return
        when (requestCode) {
            REQUEST_IMPORT -> importPlaylist(uri)
            REQUEST_EXPORT -> exporting?.let { exportPlaylist(it, uri) }
        }
    }

    private fun exportPlaylist(playlist: Playlist, uri: Uri) {
        val names = store.playlistItems(playlist.id).map { it.title }
        val message = try {
            contentResolver.openOutputStream(uri)?.use { it.write(M3u.render(names).toByteArray()) }
            R.string.playlist_exported
        } catch (_: java.io.IOException) {
            R.string.playlist_not_exported
        }
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    /** Songs are matched by file name, since paths from elsewhere mean nothing on this phone. */
    private fun importPlaylist(uri: Uri) {
        val text = try {
            contentResolver.openInputStream(uri)?.use { it.readBytes().toString(Charsets.UTF_8) }
        } catch (_: java.io.IOException) {
            null
        }
        val (found, missing) = M3u.match(M3u.fileNames(text.orEmpty()), MusicLibrary.everySong(this))
        if (found.isEmpty()) {
            Toast.makeText(this, R.string.playlist_nothing_found, Toast.LENGTH_LONG).show()
            return
        }
        val name = MusicRules.withoutExtension(PlaybackSession.get(this).displayName(uri) ?: getString(R.string.import_playlist))
        val id = store.createPlaylist(name)
        found.forEach { store.addToPlaylist(id, it.uri, it.fileName) }
        refresh()
        Toast.makeText(this, getString(R.string.playlist_imported, found.size, missing), Toast.LENGTH_LONG).show()
    }

    private fun manage(playlist: Playlist) {
        val actions = listOf(getString(R.string.rename), getString(R.string.export_playlist), getString(R.string.delete))
        AlertDialog.Builder(this)
            .setTitle(playlist.name)
            .setItems(actions.toTypedArray()) { _, which ->
                if (which == 0) {
                    askPlaylistName(this, playlist.name) { name ->
                        store.renamePlaylist(playlist.id, name)
                        refresh()
                    }
                } else if (which == 1) {
                    pickExportFile(playlist)
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
    private lateinit var nowPlaying: NowPlayingBar
    private lateinit var empty: TextView
    private var playlistId = 0L
    private var automatic: AutoList? = null
    private var items: List<PlaylistItem> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_playlists)
        applySystemBarPadding(findViewById(R.id.playlistsRoot))
        store = LibraryStore(this)
        adapter = MediaRowAdapter(this)
        nowPlaying = NowPlayingBar(this)
        playlistId = intent.getLongExtra(EXTRA_ID, 0)
        automatic = AutoList.entries.firstOrNull { it.name == intent.getStringExtra(EXTRA_AUTO) }
        findViewById<TextView>(R.id.playlistsTitle).text = intent.getStringExtra(EXTRA_NAME).orEmpty()
        empty = findViewById(R.id.playlistsEmpty)
        empty.setText(if (automatic == null) R.string.playlist_empty else R.string.auto_empty)
        findViewById<View>(R.id.bottomNav).visibility = View.GONE
        val list = findViewById<ListView>(R.id.playlistsList)
        list.adapter = adapter
        list.setOnItemClickListener { _, _, position, _ -> play(position) }
        list.setOnItemLongClickListener { _, _, position, _ ->
            when (automatic) {
                null -> manage(items[position])
                AutoList.FAVOURITES -> removeFavourite(items[position])
                else -> Unit
            }
            true
        }
        findViewById<Button>(R.id.playlistsAction).apply {
            setText(R.string.play_all)
            setCompoundDrawablesRelativeWithIntrinsicBounds(R.drawable.ic_play, 0, 0, 0)
            setOnClickListener { if (items.isNotEmpty()) play(0) }
        }
        findViewById<View>(R.id.playlistTools).visibility = View.VISIBLE
        findViewById<View>(R.id.playlistsAdd).apply {
            visibility = if (automatic == null) View.VISIBLE else View.GONE
            setOnClickListener { chooseWhereToAddFrom() }
        }
        findViewById<View>(R.id.playlistsShuffle).setOnClickListener {
            if (items.isNotEmpty()) playQueue(items.shuffled(), 0)
        }
    }

    override fun onStart() {
        super.onStart()
        refresh()
        nowPlaying.start()
    }

    override fun onStop() {
        nowPlaying.stop()
        super.onStop()
    }

    override fun onDestroy() {
        store.close()
        super.onDestroy()
    }

    private fun refresh() {
        val list = automatic
        if (list == AutoList.RECENTLY_ADDED) {
            Thread {
                val newest = MusicRules.sorted(MusicLibrary.songs(this), SongSort.RECENTLY_ADDED)
                    .take(LibraryStore.AUTOMATIC_LIST_SIZE)
                    .map { SavedTrack(it.uri, it.fileName) }
                runOnUiThread { if (!isDestroyed) showItems(saved(newest)) }
            }.start()
            return
        }
        showItems(
            when (list) {
                null -> store.playlistItems(playlistId)
                AutoList.FAVOURITES -> saved(store.favourites())
                AutoList.RECENTLY_PLAYED -> saved(store.recentlyPlayed())
                AutoList.MOST_PLAYED -> saved(store.mostPlayed())
                AutoList.RECENTLY_ADDED -> emptyList()
            },
        )
    }

    private fun saved(tracks: List<SavedTrack>) = tracks.mapIndexed { index, track ->
        PlaylistItem(index.toLong(), 0, index, track.uri, track.title)
    }

    private fun showItems(shown: List<PlaylistItem>) {
        items = shown
        adapter.rows = items.map {
            val audio = placeholderFor(it.title) == R.drawable.ic_audio
            MediaRow(
                if (audio) MusicRules.withoutExtension(it.title) else it.title,
                "",
                placeholder = placeholderFor(it.title),
                artUri = it.uri.takeIf { audio },
            )
        }
        empty.visibility = if (items.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun removeFavourite(item: PlaylistItem) {
        AlertDialog.Builder(this)
            .setTitle(MusicRules.withoutExtension(item.title))
            .setItems(arrayOf(getString(R.string.remove_favourite))) { _, _ ->
                store.setFavourite(item.uri, item.title, false)
                refresh()
            }
            .show()
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

    private fun play(index: Int) = playQueue(items, index)

    private fun playQueue(queue: List<PlaylistItem>, index: Int) {
        startActivity(
            Intent(this, PlayerActivity::class.java)
                .setData(Uri.parse(queue[index].uri))
                .putStringArrayListExtra(PlayerActivity.EXTRA_QUEUE_URIS, ArrayList(queue.map { it.uri }))
                .putStringArrayListExtra(PlayerActivity.EXTRA_QUEUE_TITLES, ArrayList(queue.map { it.title }))
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
        const val EXTRA_AUTO = "com.babarify.frame.PLAYLIST_AUTO"
        private const val REQUEST_FILES = 4
    }
}
