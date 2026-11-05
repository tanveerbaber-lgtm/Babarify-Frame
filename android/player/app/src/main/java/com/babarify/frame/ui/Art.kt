package com.babarify.frame.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Outline
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.util.LruCache
import android.util.Size
import android.view.View
import android.view.ViewOutlineProvider
import android.widget.ImageView
import com.babarify.frame.R
import java.io.IOException
import java.util.concurrent.Executors

/** Songs' pictures for lists, loaded away from the main thread and kept for a while. */
object Art {
    private const val SIZE_PX = 320
    private const val LARGE_INSET_DP = 40
    private const val CACHE_BYTES = 24 * 1024 * 1024
    private val workers = Executors.newFixedThreadPool(2)
    private val pictures = object : LruCache<String, Bitmap>(CACHE_BYTES) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }
    private val noPicture = HashSet<String>()

    /** Shows the song's picture, or [placeholder] if it has none. Safe to call again as a list row is reused. */
    fun show(
        image: ImageView,
        uri: String?,
        placeholder: Int = R.drawable.ic_audio,
        cornersDp: Float = 10f,
        largePlaceholder: Boolean = false,
        onPicture: ((Bitmap?) -> Unit)? = null,
    ) {
        val density = image.resources.displayMetrics.density
        image.outlineProvider = object : ViewOutlineProvider() {
            override fun getOutline(view: View, outline: Outline) {
                outline.setRoundRect(0, 0, view.width, view.height, cornersDp * density)
            }
        }
        image.clipToOutline = true
        image.tag = uri
        val known = uri?.let { pictures.get(it) }
        if (known != null) {
            showPicture(image, known)
            onPicture?.invoke(known)
            return
        }
        onPicture?.invoke(null)
        if (largePlaceholder) {
            val inset = (LARGE_INSET_DP * density).toInt()
            image.setPadding(inset, inset, inset, inset)
            image.scaleType = ImageView.ScaleType.FIT_CENTER
        } else {
            image.setPadding(0, 0, 0, 0)
            image.scaleType = ImageView.ScaleType.CENTER
        }
        image.imageTintList = image.context.getColorStateList(R.color.text_muted)
        image.setImageResource(placeholder)
        if (uri == null || synchronized(noPicture) { uri in noPicture }) return
        val context = image.context.applicationContext
        workers.execute {
            val loaded = load(context, Uri.parse(uri))
            if (loaded == null) {
                synchronized(noPicture) { noPicture += uri }
            } else {
                pictures.put(uri, loaded)
                image.post {
                    if (image.tag == uri) {
                        showPicture(image, loaded)
                        onPicture?.invoke(loaded)
                    }
                }
            }
        }
    }

    private fun showPicture(image: ImageView, picture: Bitmap) {
        image.imageTintList = null
        image.setPadding(0, 0, 0, 0)
        image.scaleType = ImageView.ScaleType.CENTER_CROP
        image.setImageBitmap(picture)
    }

    private fun load(context: Context, uri: Uri): Bitmap? = try {
        context.contentResolver.loadThumbnail(uri, Size(SIZE_PX, SIZE_PX), null)
    } catch (_: IOException) {
        embedded(context, uri)
    } catch (_: RuntimeException) {
        embedded(context, uri)
    }

    private fun embedded(context: Context, uri: Uri): Bitmap? {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(context, uri)
            retriever.embeddedPicture?.let { BitmapFactory.decodeByteArray(it, 0, it.size, BitmapFactory.Options().apply { inSampleSize = 2 }) }
        } catch (_: RuntimeException) {
            null
        } finally {
            try {
                retriever.release()
            } catch (_: IOException) {
                // Nothing more to do with it.
            }
        }
    }

    /** The title and artist tags, for the mini player. The answer arrives on the main thread. */
    fun tags(view: View, uri: Uri, onTags: (title: String?, artist: String?) -> Unit) {
        val context = view.context.applicationContext
        workers.execute {
            val retriever = MediaMetadataRetriever()
            var title: String? = null
            var artist: String? = null
            try {
                retriever.setDataSource(context, uri)
                title = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)
                artist = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)
            } catch (_: RuntimeException) {
                // No tags: the file's name is enough.
            } finally {
                try {
                    retriever.release()
                } catch (_: IOException) {
                    // Nothing more to do with it.
                }
            }
            view.post { onTags(title, artist) }
        }
    }

    /** A dark colour from the picture, to fill the screen around it. Dark enough for white text. */
    fun backgroundFrom(picture: Bitmap): Int {
        val one = Bitmap.createScaledBitmap(picture.copy(Bitmap.Config.ARGB_8888, false), 1, 1, true)
        val hsv = FloatArray(3)
        Color.colorToHSV(one.getPixel(0, 0), hsv)
        hsv[1] = (hsv[1] * 1.3f).coerceAtMost(0.8f)
        hsv[2] = (hsv[2] * 0.5f).coerceIn(0.1f, 0.3f)
        return Color.HSVToColor(hsv)
    }
}
