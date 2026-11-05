package com.babarify.frame.ui

import android.app.Activity
import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.view.MotionEvent
import android.view.View
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import com.babarify.frame.R
import com.babarify.frame.core.ErrorCode
import com.babarify.frame.core.MusicRules
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.engine.BackgroundPlaybackService
import com.babarify.frame.engine.PlaybackSession
import com.babarify.frame.engine.SessionListener
import kotlin.math.abs

/** Shows what's playing on after the player screen has closed, and leads back to it. */
class NowPlayingBar(private val activity: Activity) : SessionListener {
    private val session = PlaybackSession.get(activity)
    private val bar = activity.findViewById<View>(R.id.nowPlaying)
    private val art = activity.findViewById<ImageView>(R.id.nowPlayingArt)
    private val title = activity.findViewById<TextView>(R.id.nowPlayingTitle)
    private val artist = activity.findViewById<TextView>(R.id.nowPlayingArtist)
    private val toggle = activity.findViewById<ImageButton>(R.id.nowPlayingToggle)
    private val next = activity.findViewById<ImageButton>(R.id.nowPlayingNext)
    private val progress = activity.findViewById<ProgressBar>(R.id.nowPlayingProgress)
    private val density = activity.resources.displayMetrics.density
    private val light = ColourThemes.isLight(ColourThemes.current(session.preferences))
    private val handler = Handler(Looper.getMainLooper())
    private val refreshNow = Runnable { refresh() }
    private var shownFor: Uri? = null
    private val tick = object : Runnable {
        override fun run() {
            showProgress()
            handler.postDelayed(this, TICK_MS)
        }
    }
    private var touchX = 0f
    private var touchY = 0f

    init {
        bar.setOnClickListener {
            session.mediaUri?.let { uri -> activity.startActivity(Intent(activity, PlayerActivity::class.java).setData(uri)) }
        }
        // A player closed within a moment of opening never stopped this screen, so start() doesn't run again.
        bar.viewTreeObserver.addOnWindowFocusChangeListener { focused -> if (focused) refresh() }
        bar.setOnTouchListener { _, event -> followFinger(event) }
        bar.clipToOutline = true
        showCardColour(activity.themeColor(R.attr.raisedColor))
        toggle.setOnClickListener { session.togglePlay() }
        next.setOnClickListener { session.next() }
        activity.findViewById<View>(R.id.nowPlayingClose).setOnClickListener {
            bar.visibility = View.GONE
            BackgroundPlaybackService.close(activity)
        }
    }

    fun start() {
        session.addListener(this)
        refresh()
        handler.post(tick)
    }

    fun stop() {
        session.removeListener(this)
        handler.removeCallbacks(refreshNow)
        handler.removeCallbacks(tick)
    }

    /** The card follows the finger. How far it went decides, not how fast, so a slow swipe counts too. */
    private fun followFinger(event: MotionEvent): Boolean {
        val distanceX = event.rawX - touchX
        val distanceY = event.rawY - touchY
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                touchX = event.rawX
                touchY = event.rawY
                bar.animate().cancel()
            }
            MotionEvent.ACTION_MOVE -> bar.translationX = distanceX
            MotionEvent.ACTION_UP -> {
                bar.animate().translationX(0f).setDuration(SETTLE_CARD_MS).start()
                when {
                    abs(distanceX) >= SWIPE_DP * density && abs(distanceX) > abs(distanceY) * 2 ->
                        if (distanceX < 0) session.next() else session.previous()
                    abs(distanceX) < TAP_DP * density && abs(distanceY) < TAP_DP * density -> bar.performClick()
                }
            }
            MotionEvent.ACTION_CANCEL -> bar.animate().translationX(0f).setDuration(SETTLE_CARD_MS).start()
        }
        return true
    }

    /** The card takes a dark colour from the song's picture. */
    private fun showCardColour(colour: Int) {
        bar.background = GradientDrawable().apply {
            setColor(colour)
            cornerRadius = CARD_CORNERS_DP * density
        }
    }

    private fun showProgress() {
        val duration = session.durationMs
        progress.progress = if (duration != null && duration > 0) {
            (session.positionMs * progress.max / duration).toInt().coerceIn(0, progress.max)
        } else {
            0
        }
    }

    private fun refresh() {
        val state = session.state
        val active = state == PlaybackState.PLAYING || state == PlaybackState.PAUSED
        bar.visibility = if (active && !PlayerActivity.isInFront) View.VISIBLE else View.GONE
        if (session.mediaUri != shownFor) title.text = MusicRules.withoutExtension(session.title)
        val playing = session.isPlaying
        toggle.setImageResource(if (playing) R.drawable.ic_pause else R.drawable.ic_play)
        toggle.contentDescription = activity.getString(if (playing) R.string.pause else R.string.play)
        next.visibility = if (session.queue.isPlaylist) View.VISIBLE else View.GONE
        val uri = session.mediaUri
        if (active && uri != null && uri != shownFor) {
            shownFor = uri
            val audio = !PlaybackRules.isVideoName(session.title)
            Art.show(art, uri.toString(), if (audio) R.drawable.ic_audio else R.drawable.ic_movie, ART_CORNERS_DP) { picture ->
                showCardColour(picture?.let { Art.backgroundFrom(it, light) } ?: activity.themeColor(R.attr.raisedColor))
            }
            artist.visibility = View.GONE
            Art.tags(bar, uri) { songTitle, name ->
                if (shownFor == uri) {
                    MusicRules.tagOrNull(songTitle)?.takeIf { audio }?.let { title.text = it }
                    val tag = MusicRules.tagOrNull(name)
                    artist.text = tag.orEmpty()
                    artist.visibility = if (tag == null) View.GONE else View.VISIBLE
                }
            }
        }
    }

    override fun onPlaybackStateChanged(state: PlaybackState, error: ErrorCode?) {
        // The mini player reacts to the same news, and may be about to close everything.
        handler.removeCallbacks(refreshNow)
        handler.postDelayed(refreshNow, SETTLE_MS)
    }

    override fun onMediaChanged() = refresh()

    private companion object {
        const val SETTLE_MS = 200L
        const val ART_CORNERS_DP = 24f
        const val CARD_CORNERS_DP = 18f
        const val SWIPE_DP = 60
        const val TAP_DP = 12
        const val SETTLE_CARD_MS = 150L
        const val TICK_MS = 500L
    }
}
