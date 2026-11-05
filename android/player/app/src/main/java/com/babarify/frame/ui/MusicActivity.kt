package com.babarify.frame.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.text.Editable
import android.text.TextWatcher
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.GridView
import android.widget.ImageView
import android.widget.ListView
import android.widget.TextView
import android.widget.Toast
import com.babarify.frame.R
import com.babarify.frame.core.GroupKind
import com.babarify.frame.core.MusicRules
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.core.QueueItem
import com.babarify.frame.core.Song
import com.babarify.frame.core.SongGroup
import com.babarify.frame.core.SongSort
import com.babarify.frame.data.LibraryStore
import com.babarify.frame.data.MusicLibrary
import com.babarify.frame.engine.PlaybackSession
import java.util.concurrent.Executors
import kotlin.math.abs

/** Plays songs one after another. Handed over directly: a big collection wouldn't fit in an Intent. */
fun Activity.playSongs(songs: List<Song>, index: Int, shuffle: Boolean = false) {
    if (songs.isEmpty()) return
    PlayerActivity.pendingQueue = songs.map { QueueItem(it.uri, it.fileName) }
    startActivity(
        Intent(this, PlayerActivity::class.java)
            .setData(Uri.parse(songs[index].uri))
            .putExtra(PlayerActivity.EXTRA_QUEUE_INDEX, index)
            .putExtra(PlayerActivity.EXTRA_SHUFFLE, shuffle),
    )
}

fun songCount(context: Context, count: Int): String =
    if (count == 1) context.getString(R.string.song_count_one) else context.getString(R.string.song_count, count)

/** A square as wide as its column. */
class SquareImageView @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : ImageView(context, attrs) {
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        super.onMeasure(widthMeasureSpec, widthMeasureSpec)
    }
}

class SongAdapter(private val activity: Activity, private val store: LibraryStore) : BaseAdapter() {
    private val inflater = LayoutInflater.from(activity)
    var songs: List<Song> = emptyList()
        set(value) {
            field = value
            notifyDataSetChanged()
        }

    override fun getCount() = songs.size
    override fun getItem(position: Int) = songs[position]
    override fun getItemId(position: Int) = position.toLong()

    override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
        val view = convertView ?: inflater.inflate(R.layout.item_song, parent, false)
        val song = songs[position]
        val playing = PlaybackSession.get(activity).mediaUri?.toString() == song.uri
        view.findViewById<TextView>(R.id.songTitle).apply {
            text = song.title
            setTextColor(if (playing) context.themeColor(R.attr.accent2Color) else context.getColor(R.color.text))
        }
        view.findViewById<TextView>(R.id.songDetail).text = activity.getString(
            R.string.song_detail,
            song.artist ?: activity.getString(R.string.unknown_artist),
            PlaybackRules.formatTime(song.durationMs),
        )
        Art.show(view.findViewById(R.id.songArt), song.uri)
        view.findViewById<View>(R.id.songMore).setOnClickListener { showSongActions(activity, store, song) }
        return view
    }
}

fun showSongActions(activity: Activity, store: LibraryStore, song: Song) {
    val favourite = store.isFavourite(song.uri)
    val actions = listOf(
        activity.getString(if (favourite) R.string.remove_favourite else R.string.add_favourite),
        activity.getString(R.string.add_to_playlist),
    )
    AlertDialog.Builder(activity)
        .setTitle(song.title)
        .setItems(actions.toTypedArray()) { _, which ->
            if (which == 0) {
                store.setFavourite(song.uri, song.fileName, !favourite)
            } else {
                chooseSongPlaylist(activity, store, song)
            }
        }
        .show()
}

private fun chooseSongPlaylist(activity: Activity, store: LibraryStore, song: Song) {
    val playlists = store.playlists()
    val labels = playlists.map { it.name } + activity.getString(R.string.new_playlist)
    fun add(id: Long, name: String) {
        store.addToPlaylist(id, song.uri, song.fileName)
        Toast.makeText(activity, activity.getString(R.string.added_to_playlist, name), Toast.LENGTH_SHORT).show()
    }
    AlertDialog.Builder(activity)
        .setTitle(R.string.add_to_playlist)
        .setItems(labels.toTypedArray()) { _, which ->
            val playlist = playlists.getOrNull(which)
            if (playlist != null) {
                add(playlist.id, playlist.name)
            } else {
                askPlaylistName(activity, null) { name -> add(store.createPlaylist(name), name) }
            }
        }
        .show()
}

/** Albums as a grid; artists and folders as rows. */
private class GroupAdapter(private val activity: Activity, private val grid: Boolean) : BaseAdapter() {
    private val inflater = LayoutInflater.from(activity)
    var groups: List<SongGroup> = emptyList()
        set(value) {
            field = value
            notifyDataSetChanged()
        }

    override fun getCount() = groups.size
    override fun getItem(position: Int) = groups[position]
    override fun getItemId(position: Int) = position.toLong()

    override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
        val group = groups[position]
        val count = songCount(activity, group.songs.size)
        if (grid) {
            val view = convertView ?: inflater.inflate(R.layout.item_album, parent, false)
            view.findViewById<TextView>(R.id.albumTitle).text = groupTitle(activity, group)
            view.findViewById<TextView>(R.id.albumDetail).text = group.songs.first().artist ?: count
            Art.show(view.findViewById(R.id.albumArt), group.songs.first().uri, R.drawable.ic_album, 12f, largePlaceholder = true)
            return view
        }
        val view = convertView ?: inflater.inflate(R.layout.item_song, parent, false)
        view.findViewById<TextView>(R.id.songTitle).text = groupTitle(activity, group)
        view.findViewById<TextView>(R.id.songDetail).text = count
        view.findViewById<View>(R.id.songMore).visibility = View.GONE
        val folder = group.kind == GroupKind.FOLDER
        Art.show(
            view.findViewById(R.id.songArt),
            if (folder) null else group.songs.first().uri,
            if (folder) R.drawable.ic_folder else R.drawable.ic_artist,
            if (folder) 10f else 28f,
        )
        return view
    }
}

fun groupTitle(context: Context, group: SongGroup): String = group.title.ifEmpty {
    context.getString(
        when (group.kind) {
            GroupKind.ALBUM -> R.string.unknown_album
            GroupKind.ARTIST -> R.string.unknown_artist
            GroupKind.FOLDER -> R.string.internal_storage
        },
    )
}

/** Every song on the phone, by song, album, artist and folder, once the user allows it. */
class MusicActivity : Activity() {
    private lateinit var store: LibraryStore
    private lateinit var session: PlaybackSession
    private lateinit var nowPlaying: NowPlayingBar
    private lateinit var songAdapter: SongAdapter
    private lateinit var albumAdapter: GroupAdapter
    private lateinit var rowAdapter: GroupAdapter
    private lateinit var list: ListView
    private lateinit var grid: GridView
    private lateinit var search: EditText
    private lateinit var prompt: View
    private lateinit var actions: View
    private lateinit var swipes: GestureDetector
    private val worker = Executors.newSingleThreadExecutor()
    private var allSongs: List<Song> = emptyList()
    private var shown: List<Song> = emptyList()
    private var loaded = false
    private var tab = 0
    private var refused = false
    private val tabs by lazy { listOf(R.id.tabSongs, R.id.tabAlbums, R.id.tabArtists, R.id.tabFolders).map { findViewById<TextView>(it) } }

    /** For tests. */
    val shownSongs: List<Song> get() = shown
    val shownGroups: List<SongGroup> get() = currentGroups()
    val isLoaded: Boolean get() = loaded
    val currentTab: Int get() = tab
    val promptVisible: Boolean get() = prompt.visibility == View.VISIBLE
    fun chooseTab(index: Int) = selectTab(index)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_music)
        applySystemBarPadding(findViewById(R.id.musicRoot))
        store = LibraryStore(this)
        session = PlaybackSession.get(this)
        nowPlaying = NowPlayingBar(this)
        BottomNav.attach(this, findViewById(R.id.bottomNav))
        songAdapter = SongAdapter(this, store)
        albumAdapter = GroupAdapter(this, grid = true)
        rowAdapter = GroupAdapter(this, grid = false)
        list = findViewById(R.id.musicList)
        grid = findViewById(R.id.musicGrid)
        search = findViewById(R.id.musicSearch)
        prompt = findViewById(R.id.musicPrompt)
        actions = findViewById(R.id.musicActions)
        grid.adapter = albumAdapter
        grid.setOnItemClickListener { _, _, position, _ -> openGroup(albumAdapter.groups[position]) }
        list.setOnItemClickListener { _, _, position, _ ->
            if (tab == 0) playSongs(shown, position) else openGroup(rowAdapter.groups[position])
        }
        list.setOnItemLongClickListener { _, _, position, _ ->
            if (tab == 0) showSongActions(this, store, shown[position])
            tab == 0
        }
        tabs.forEachIndexed { index, view -> view.setOnClickListener { selectTab(index) } }
        findViewById<View>(R.id.musicShuffle).setOnClickListener {
            if (shown.isNotEmpty()) playSongs(shown, shown.indices.random(), shuffle = true)
        }
        findViewById<View>(R.id.musicPlay).setOnClickListener { playSongs(shown, 0) }
        findViewById<View>(R.id.musicSortButton).setOnClickListener { chooseSort() }
        findViewById<View>(R.id.musicSearchButton).setOnClickListener {
            val showing = search.visibility == View.VISIBLE
            search.visibility = if (showing) View.GONE else View.VISIBLE
            if (showing) search.setText("") else search.requestFocus()
        }
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) = show()
        })
        findViewById<Button>(R.id.musicPromptButton).setOnClickListener { askOrOpenSettings() }
        swipes = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onFling(first: MotionEvent?, last: MotionEvent, speedX: Float, speedY: Float): Boolean {
                val start = first ?: return false
                val card = findViewById<View>(R.id.nowPlaying)
                val cardAt = IntArray(2).also(card::getLocationOnScreen)
                if (card.visibility == View.VISIBLE && start.rawY >= cardAt[1]) return false
                val distance = last.x - start.x
                if (abs(distance) < SWIPE_DP * resources.displayMetrics.density || abs(speedX) < abs(speedY) * 2) return false
                selectTab((tab + if (distance < 0) 1 else -1).coerceIn(tabs.indices))
                return true
            }
        })
        selectTab(0)
    }

    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        swipes.onTouchEvent(event)
        return super.dispatchTouchEvent(event)
    }

    override fun onStart() {
        super.onStart()
        nowPlaying.start()
        reload()
    }

    override fun onStop() {
        nowPlaying.stop()
        super.onStop()
    }

    override fun onDestroy() {
        worker.shutdownNow()
        store.close()
        super.onDestroy()
    }

    private fun reload() {
        if (!MusicLibrary.allowed(this)) {
            showPrompt()
            return
        }
        prompt.visibility = View.GONE
        worker.execute {
            val songs = MusicLibrary.songs(this)
            runOnUiThread {
                if (!isDestroyed) {
                    allSongs = songs
                    loaded = true
                    show()
                }
            }
        }
    }

    private fun showPrompt() {
        loaded = true
        actions.visibility = View.GONE
        list.visibility = View.GONE
        grid.visibility = View.GONE
        prompt.visibility = View.VISIBLE
        findViewById<TextView>(R.id.musicPromptText).setText(if (refused) R.string.music_permission_denied else R.string.music_permission_ask)
        findViewById<Button>(R.id.musicPromptButton).apply {
            visibility = View.VISIBLE
            setText(if (refused) R.string.open_app_settings else R.string.find_my_music)
        }
    }

    private fun askOrOpenSettings() {
        if (refused && !shouldShowRequestPermissionRationale(MusicLibrary.permission)) {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", packageName, null)))
        } else {
            requestPermissions(arrayOf(MusicLibrary.permission), REQUEST_MUSIC)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_MUSIC) return
        refused = !MusicLibrary.allowed(this)
        reload()
    }

    private fun selectTab(index: Int) {
        tab = index
        tabs.forEachIndexed { position, view ->
            view.isSelected = position == index
            view.setTextColor(getColor(if (position == index) R.color.text else R.color.text_muted))
        }
        show()
    }

    private fun currentGroups(): List<SongGroup> {
        val kind = when (tab) {
            1 -> GroupKind.ALBUM
            2 -> GroupKind.ARTIST
            3 -> GroupKind.FOLDER
            else -> return emptyList()
        }
        return MusicRules.groups(MusicRules.search(allSongs, search.text.toString()), kind)
    }

    private fun show() {
        if (prompt.visibility == View.VISIBLE && !MusicLibrary.allowed(this)) return
        shown = MusicRules.sorted(MusicRules.search(allSongs, search.text.toString()), session.preferences.musicSort)
        val empty = loaded && allSongs.isEmpty()
        prompt.visibility = if (empty) View.VISIBLE else View.GONE
        if (empty) {
            findViewById<TextView>(R.id.musicPromptText).setText(R.string.no_music_found)
            findViewById<View>(R.id.musicPromptButton).visibility = View.GONE
        }
        val albums = tab == 1
        grid.visibility = if (albums && !empty) View.VISIBLE else View.GONE
        list.visibility = if (!albums && !empty) View.VISIBLE else View.GONE
        actions.visibility = if (tab == 0 && !empty && allSongs.isNotEmpty()) View.VISIBLE else View.GONE
        findViewById<TextView>(R.id.musicCount).text = songCount(this, shown.size)
        when (tab) {
            0 -> {
                if (list.adapter !== songAdapter) list.adapter = songAdapter
                songAdapter.songs = shown
            }
            1 -> albumAdapter.groups = currentGroups()
            else -> {
                if (list.adapter !== rowAdapter) list.adapter = rowAdapter
                rowAdapter.groups = currentGroups()
            }
        }
    }

    private fun chooseSort() {
        val orders = SongSort.entries
        val labels = listOf(R.string.sort_title, R.string.sort_artist, R.string.sort_date_added, R.string.sort_duration).map(::getString)
        AlertDialog.Builder(this)
            .setTitle(R.string.sort)
            .setSingleChoiceItems(labels.toTypedArray(), orders.indexOf(session.preferences.musicSort)) { dialog, which ->
                session.preferences.musicSort = orders[which]
                show()
                dialog.dismiss()
            }
            .show()
    }

    private fun openGroup(group: SongGroup) {
        startActivity(
            Intent(this, MusicGroupActivity::class.java)
                .putExtra(MusicGroupActivity.EXTRA_KIND, group.kind.name)
                .putExtra(MusicGroupActivity.EXTRA_KEY, group.key),
        )
    }

    private companion object {
        const val REQUEST_MUSIC = 5
        const val SWIPE_DP = 80
    }
}

/** One album, artist or folder. */
class MusicGroupActivity : Activity() {
    private lateinit var store: LibraryStore
    private lateinit var nowPlaying: NowPlayingBar
    private lateinit var adapter: SongAdapter
    private val worker = Executors.newSingleThreadExecutor()
    private var songs: List<Song> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_music_group)
        applySystemBarPadding(findViewById(R.id.groupRoot))
        store = LibraryStore(this)
        nowPlaying = NowPlayingBar(this)
        adapter = SongAdapter(this, store)
        val list = findViewById<ListView>(R.id.groupList)
        val header = layoutInflater.inflate(R.layout.header_music_group, list, false)
        list.addHeaderView(header, null, false)
        list.adapter = adapter
        list.setOnItemClickListener { _, _, position, _ -> playSongs(songs, position - list.headerViewsCount) }
        findViewById<View>(R.id.groupBack).setOnClickListener { finish() }
        header.findViewById<View>(R.id.groupShuffle).setOnClickListener {
            if (songs.isNotEmpty()) playSongs(songs, songs.indices.random(), shuffle = true)
        }
        header.findViewById<View>(R.id.groupPlay).setOnClickListener { playSongs(songs, 0) }
        val kind = GroupKind.entries.firstOrNull { it.name == intent.getStringExtra(EXTRA_KIND) } ?: GroupKind.ALBUM
        val key = intent.getStringExtra(EXTRA_KEY).orEmpty()
        worker.execute {
            val group = MusicRules.groups(MusicLibrary.songs(this), kind).firstOrNull { it.key == key }
            runOnUiThread { if (!isDestroyed) show(header, group) }
        }
    }

    private fun show(header: View, group: SongGroup?) {
        if (group == null) {
            finish()
            return
        }
        songs = group.songs
        adapter.songs = songs
        header.findViewById<TextView>(R.id.groupTitle).text = groupTitle(this, group)
        header.findViewById<TextView>(R.id.groupCount).text = songCount(this, songs.size)
        Art.show(
            header.findViewById(R.id.groupArt),
            songs.first().uri.takeIf { group.kind != GroupKind.FOLDER },
            if (group.kind == GroupKind.FOLDER) R.drawable.ic_folder else R.drawable.ic_album,
            16f,
            largePlaceholder = true,
        )
    }

    override fun onStart() {
        super.onStart()
        nowPlaying.start()
        adapter.notifyDataSetChanged()
    }

    override fun onStop() {
        nowPlaying.stop()
        super.onStop()
    }

    override fun onDestroy() {
        worker.shutdownNow()
        store.close()
        super.onDestroy()
    }

    companion object {
        const val EXTRA_KIND = "com.babarify.frame.GROUP_KIND"
        const val EXTRA_KEY = "com.babarify.frame.GROUP_KEY"
    }
}
