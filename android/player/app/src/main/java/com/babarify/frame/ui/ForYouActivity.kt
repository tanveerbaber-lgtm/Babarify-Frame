package com.babarify.frame.ui

import android.app.Activity
import android.os.Bundle
import android.util.TypedValue
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.babarify.frame.R
import com.babarify.frame.core.Recap
import com.babarify.frame.core.Song
import com.babarify.frame.data.LibraryStore
import com.babarify.frame.data.MusicLibrary
import java.util.concurrent.Executors

/** A recap of what's been played, and what to play next. Everything is worked out on this phone. */
class ForYouActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private lateinit var column: LinearLayout

    /** For tests. */
    var shown: Recap? = null
        private set

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val scroll = ScrollView(this)
        column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(12), dp(16), dp(24))
        }
        scroll.addView(column)
        setContentView(scroll)
        applySystemBarPadding(scroll)
    }

    override fun onStart() {
        super.onStart()
        worker.execute {
            val songs = MusicLibrary.songs(this)
            val recap = LibraryStore(this).use { Recap.of(songs, it.playCounts()) }
            runOnUiThread { if (!isDestroyed) show(songs, recap) }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        worker.shutdown()
    }

    private fun show(songs: List<Song>, recap: Recap) {
        shown = recap
        column.removeAllViews()
        column.addView(
            LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
                addView(
                    ImageButton(context, null, 0, R.style.IconButton).apply {
                        setImageResource(R.drawable.ic_arrow_back)
                        contentDescription = getString(R.string.back)
                        setOnClickListener { finish() }
                    },
                )
                addView(text(getString(R.string.for_you), 28f, R.style.Text_Title).apply { setPadding(dp(8), 0, 0, 0) })
            },
        )
        column.addView(text(summary(recap), 16f, R.style.Text_Body).apply { setPadding(0, dp(8), 0, dp(8)) })
        songSection(R.string.most_played, recap.topSongs.map { (song, times) -> song to plays(times) })
        groupSection(R.string.top_artists, recap.topArtists, songs) { it.artist }
        groupSection(R.string.top_albums, recap.topAlbums, songs) { it.album }
        songSection(R.string.never_played, recap.neverPlayed.map { it to it.artist.orEmpty() })
    }

    private fun summary(recap: Recap): String {
        if (recap.plays == 0) return getString(R.string.recap_empty)
        val minutes = recap.listenedMs / 60_000
        val time = if (minutes >= 60) {
            getString(R.string.listening_hours, minutes / 60, minutes % 60)
        } else {
            getString(R.string.listening_minutes, minutes)
        }
        val times = resources.getQuantityString(R.plurals.times_count, recap.plays, recap.plays)
        return getString(R.string.recap_summary, songCount(this, recap.songsPlayed), times, time)
    }

    private fun plays(times: Int) = resources.getQuantityString(R.plurals.plays_count, times, times)

    private fun songSection(title: Int, rows: List<Pair<Song, String>>) {
        if (rows.isEmpty()) return
        heading(title)
        val songs = rows.map { it.first }
        rows.forEachIndexed { index, (song, detail) ->
            row(song.title, detail) { playSongs(songs, index) }
        }
    }

    private fun groupSection(title: Int, rows: List<Pair<String, Int>>, songs: List<Song>, name: (Song) -> String?) {
        if (rows.isEmpty()) return
        heading(title)
        rows.forEach { (group, times) ->
            row(group, plays(times)) { playSongs(songs.filter { name(it) == group }, 0) }
        }
    }

    private fun heading(title: Int) {
        column.addView(
            text(getString(title), 13f, R.style.Text_Section).apply { setPadding(0, dp(16), 0, dp(4)) },
        )
    }

    private fun row(title: String, detail: String, onClick: () -> Unit) {
        column.addView(
            LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                minimumHeight = dp(56)
                gravity = android.view.Gravity.CENTER_VERTICAL
                setBackgroundResource(R.drawable.bg_row)
                setPadding(dp(8), dp(6), dp(8), dp(6))
                isClickable = true
                isFocusable = true
                setOnClickListener { onClick() }
                addView(text(title, 16f, R.style.Text_Body))
                if (detail.isNotEmpty()) addView(text(detail, 13f, R.style.Text_Muted))
            },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT),
        )
    }

    private fun text(value: String, size: Float, style: Int) = TextView(this).apply {
        setTextAppearance(style)
        setTextSize(TypedValue.COMPLEX_UNIT_SP, size)
        text = value
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
