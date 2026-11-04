package com.babarify.frame.engine

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.drawable.Icon
import android.media.MediaMetadata
import android.media.MediaMetadataRetriever
import android.media.session.MediaSession
import android.media.session.PlaybackState as MediaPlaybackState
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import com.babarify.frame.R
import com.babarify.frame.core.ErrorCode
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.core.RepeatMode
import com.babarify.frame.ui.PlayerActivity
import java.io.IOException
import java.util.concurrent.Executors

/**
 * The mini player: keeps sound going after the player screen or the whole app has gone, for audio
 * files, and for video when the user chose that in Settings. The notification is how they see it
 * is happening, and only that notification closes it.
 */
class BackgroundPlaybackService : Service(), SessionListener {
    private lateinit var session: PlaybackSession
    private lateinit var mediaSession: MediaSession
    private lateinit var wakeLock: PowerManager.WakeLock
    private val handler = Handler(Looper.getMainLooper())
    private val refreshAgain = Runnable { refresh() }
    private val worker = Executors.newSingleThreadExecutor()
    private var cover: Bitmap? = null
    private var closing = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        running = true
        session = PlaybackSession.get(this)
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, getString(R.string.channel_playback), NotificationManager.IMPORTANCE_LOW).apply {
                setShowBadge(false)
            },
        )
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "babarify:background-audio")
            .apply { setReferenceCounted(false) }
        mediaSession = MediaSession(this, "BabarifyFrame").apply {
            setCallback(object : MediaSession.Callback() {
                override fun onPlay() = session.resume()
                override fun onPause() = session.pause()
                override fun onSkipToNext() {
                    session.next()
                }
                override fun onSkipToPrevious() = session.previous()
                override fun onSeekTo(pos: Long) {
                    session.seekTo(pos)
                    refresh()
                }
                override fun onStop() = stopEverything()
                override fun onCustomAction(action: String, extras: Bundle?) {
                    if (action == ACTION_STOP) stopEverything()
                }
            })
            isActive = true
        }
        session.addListener(this)
        loadCover()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Android requires this promptly after every start, whatever the start asked for.
        startForeground(NOTIFICATION_ID, buildNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        when (intent?.action) {
            ACTION_TOGGLE -> session.togglePlay()
            ACTION_NEXT -> session.next()
            ACTION_PREVIOUS -> session.previous()
            ACTION_STOP -> stopEverything()
        }
        refresh()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        session.removeListener(this)
        closing = true
        running = false
        handler.removeCallbacksAndMessages(null)
        worker.shutdownNow()
        // Android removes a foreground service's notification, but not one posted just as it stops.
        getSystemService(NotificationManager::class.java).cancel(NOTIFICATION_ID)
        if (wakeLock.isHeld) wakeLock.release()
        mediaSession.release()
        super.onDestroy()
    }

    override fun onPlaybackStateChanged(state: PlaybackState, error: ErrorCode?) {
        if (state == PlaybackState.ENDED || state == PlaybackState.ERROR) {
            if (!PlayerActivity.isVisible) session.stop()
            close()
            return
        }
        refresh()
        // The file's length is often known only just after it starts.
        handler.removeCallbacks(refreshAgain)
        handler.postDelayed(refreshAgain, REFRESH_AFTER_START_MS)
    }

    override fun onMediaChanged() {
        loadCover()
        refresh()
    }

    /** The picture inside a music file, if it has one. Read away from the main thread. */
    private fun loadCover() {
        val uri = session.mediaUri ?: return
        cover = null
        worker.execute {
            val retriever = MediaMetadataRetriever()
            val picture = try {
                retriever.setDataSource(this, uri)
                retriever.embeddedPicture?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
            } catch (_: RuntimeException) {
                null
            } finally {
                try {
                    retriever.release()
                } catch (_: IOException) {
                    // Nothing more to do with it.
                }
            }
            handler.post {
                if (session.mediaUri == uri) {
                    cover = picture
                    refresh()
                }
            }
        }
    }

    private fun stopEverything() {
        session.stop()
        session.wantsToPlay = false
        session.clearMedia()
        PlayerActivity.closeRequested?.invoke()
        close()
    }

    /** Nothing may redraw the notification after this, or a dead one would stay behind. */
    private fun close() {
        closing = true
        handler.removeCallbacksAndMessages(null)
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun refresh() {
        if (closing) return
        val playing = session.isPlaying
        if (playing) wakeLock.acquire(WAKE_LOCK_MS) else if (wakeLock.isHeld) wakeLock.release()
        mediaSession.setMetadata(
            MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, session.title)
                .putLong(MediaMetadata.METADATA_KEY_DURATION, session.durationMs ?: -1)
                .apply { cover?.let { putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, it) } }
                .build(),
        )
        var actions = MediaPlaybackState.ACTION_PLAY_PAUSE or MediaPlaybackState.ACTION_PLAY or
            MediaPlaybackState.ACTION_PAUSE or MediaPlaybackState.ACTION_SEEK_TO or MediaPlaybackState.ACTION_STOP or
            MediaPlaybackState.ACTION_SKIP_TO_PREVIOUS
        if (session.queue.hasNext || session.repeatMode == RepeatMode.ALL) {
            actions = actions or MediaPlaybackState.ACTION_SKIP_TO_NEXT
        }
        mediaSession.setPlaybackState(
            MediaPlaybackState.Builder()
                .setActions(actions)
                .setState(
                    if (playing) MediaPlaybackState.STATE_PLAYING else MediaPlaybackState.STATE_PAUSED,
                    session.positionMs,
                    if (playing) session.rate else 0f,
                )
                // Android 13+ builds its media controls from here, not from the notification's own buttons.
                .addCustomAction(ACTION_STOP, getString(R.string.close_mini_player), android.R.drawable.ic_menu_close_clear_cancel)
                .build(),
        )
        postNotification()
    }

    // Media session notifications are exempt from POST_NOTIFICATIONS, which this app does not ask for.
    @SuppressLint("NotificationPermission")
    private fun postNotification() {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification())
    }

    private fun buildNotification(): Notification {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, PlayerActivity::class.java)
                .setData(session.mediaUri)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val playing = session.isPlaying
        val builder = Notification.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(session.title.ifEmpty { getString(R.string.app_name) })
            .setContentIntent(open)
            .setOngoing(playing)
            .setDeleteIntent(serviceIntent(ACTION_STOP))
            .apply { cover?.let { setLargeIcon(it) } }
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .addAction(action(android.R.drawable.ic_media_previous, R.string.previous, ACTION_PREVIOUS))
            .addAction(
                action(
                    if (playing) android.R.drawable.ic_media_pause else android.R.drawable.ic_media_play,
                    if (playing) R.string.pause else R.string.play,
                    ACTION_TOGGLE,
                ),
            )
            .addAction(action(android.R.drawable.ic_media_next, R.string.next, ACTION_NEXT))
            .addAction(action(android.R.drawable.ic_menu_close_clear_cancel, R.string.stop, ACTION_STOP))
            .setStyle(Notification.MediaStyle().setMediaSession(mediaSession.sessionToken).setShowActionsInCompactView(1, 3))
        return builder.build()
    }

    private fun action(icon: Int, label: Int, name: String): Notification.Action {
        return Notification.Action.Builder(Icon.createWithResource(this, icon), getString(label), serviceIntent(name)).build()
    }

    private fun serviceIntent(name: String): PendingIntent = PendingIntent.getService(
        this,
        name.hashCode(),
        Intent(this, BackgroundPlaybackService::class.java).setAction(name),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    companion object {
        private const val CHANNEL = "playback"
        private const val NOTIFICATION_ID = 1
        private const val REFRESH_AFTER_START_MS = 1_000L
        private const val WAKE_LOCK_MS = 6L * 60 * 60 * 1000
        private const val ACTION_TOGGLE = "com.babarify.frame.action.TOGGLE"
        private const val ACTION_NEXT = "com.babarify.frame.action.NEXT"
        private const val ACTION_PREVIOUS = "com.babarify.frame.action.PREVIOUS"
        private const val ACTION_STOP = "com.babarify.frame.action.STOP"

        var running = false
            private set

        fun start(context: Context) {
            context.startForegroundService(Intent(context, BackgroundPlaybackService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, BackgroundPlaybackService::class.java))
        }
    }
}
