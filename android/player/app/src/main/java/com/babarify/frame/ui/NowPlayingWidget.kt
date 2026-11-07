package com.babarify.frame.ui

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.view.View
import android.widget.RemoteViews
import com.babarify.frame.R
import com.babarify.frame.core.MusicRules
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.engine.PlaybackSession
import java.util.concurrent.Executors

/** Play controls on the home screen. With nothing playing, every part of it opens the app. */
class NowPlayingWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) = refresh(context)

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        val session = PlaybackSession.get(context)
        when (intent.action) {
            ACTION_TOGGLE -> session.togglePlay()
            ACTION_NEXT -> session.next()
            else -> return
        }
        refresh(context)
    }

    companion object {
        private const val ACTION_TOGGLE = "com.babarify.frame.widget.TOGGLE"
        private const val ACTION_NEXT = "com.babarify.frame.widget.NEXT"
        private const val PICTURE_SIZE = 256
        private val worker = Executors.newSingleThreadExecutor()

        /** Shows what's playing now. Does nothing when no widget has been added. */
        fun refresh(context: Context) {
            val app = context.applicationContext
            val manager = AppWidgetManager.getInstance(app)
            val widgets = ComponentName(app, NowPlayingWidget::class.java)
            if (manager.getAppWidgetIds(widgets).isEmpty()) return
            val session = PlaybackSession.get(app)
            val active = session.state == PlaybackState.PLAYING || session.state == PlaybackState.PAUSED
            val uri = session.mediaUri.takeIf { active }
            val playing = session.isPlaying
            val fallback = session.title
            val hasNext = session.queue.isPlaylist
            worker.execute {
                val tags = uri?.let { readTags(app, it) }
                val title = tags?.title ?: MusicRules.withoutExtension(fallback)
                val views = views(app, uri != null, title, tags?.artist, playing, hasNext, tags?.picture)
                manager.updateAppWidget(widgets, views)
            }
        }

        fun views(
            context: Context,
            active: Boolean,
            title: String,
            artist: String?,
            playing: Boolean,
            hasNext: Boolean,
            picture: Bitmap?,
        ): RemoteViews {
            val open = PendingIntent.getActivity(
                context,
                0,
                Intent(context, if (active) PlayerActivity::class.java else HomeActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            return RemoteViews(context.packageName, R.layout.widget_now_playing).apply {
                setTextViewText(R.id.widgetTitle, if (active) title else context.getString(R.string.app_name))
                setTextViewText(R.id.widgetArtist, if (active) artist.orEmpty() else context.getString(R.string.widget_nothing_playing))
                if (picture != null) {
                    setImageViewBitmap(R.id.widgetArt, picture)
                } else {
                    setImageViewResource(R.id.widgetArt, R.mipmap.ic_launcher)
                }
                setImageViewResource(R.id.widgetToggle, if (playing) R.drawable.ic_pause else R.drawable.ic_play)
                setContentDescription(R.id.widgetToggle, context.getString(if (playing) R.string.pause else R.string.play))
                setViewVisibility(R.id.widgetNext, if (active && hasNext) View.VISIBLE else View.GONE)
                setOnClickPendingIntent(R.id.widgetRoot, open)
                setOnClickPendingIntent(R.id.widgetToggle, if (active) broadcast(context, ACTION_TOGGLE) else open)
                setOnClickPendingIntent(R.id.widgetNext, broadcast(context, ACTION_NEXT))
            }
        }

        private fun broadcast(context: Context, action: String): PendingIntent = PendingIntent.getBroadcast(
            context,
            action.hashCode(),
            Intent(context, NowPlayingWidget::class.java).setAction(action),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        private class Tags(val title: String?, val artist: String?, val picture: Bitmap?)

        private fun readTags(context: Context, uri: Uri): Tags? {
            val retriever = MediaMetadataRetriever()
            return try {
                retriever.setDataSource(context, uri)
                Tags(
                    MusicRules.tagOrNull(retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)),
                    MusicRules.tagOrNull(retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)),
                    retriever.embeddedPicture?.let { bytes ->
                        android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                            ?.let { Bitmap.createScaledBitmap(it, PICTURE_SIZE, PICTURE_SIZE, true) }
                    },
                )
            } catch (_: RuntimeException) {
                null // A file that can't be read shows its name instead.
            } finally {
                retriever.release()
            }
        }
    }
}
