package com.babarify.frame.ui

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Outline
import android.util.LruCache
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.ViewOutlineProvider
import android.widget.BaseAdapter
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import com.babarify.frame.R
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.data.LibraryScanner
import java.io.File

data class MediaRow(
    val title: String,
    val detail: String,
    val thumbnail: String? = null,
    val progress: Float? = null,
    val placeholder: Int = R.drawable.ic_movie,
    /** A song or other file to take the picture from, instead of [thumbnail]. */
    val artUri: String? = null,
    /** A colour for the icon of a list that has no picture of its own. */
    val iconColour: Int? = null,
)

/** The picture to show for a file that has none of its own, from its name. */
fun placeholderFor(name: String): Int =
    if (PlaybackRules.isMediaName(name) && !PlaybackRules.isVideoName(name)) R.drawable.ic_audio else R.drawable.ic_movie

/** The one list row used by the home screen, the library and playlists. */
class MediaRowAdapter(private val context: Context) : BaseAdapter() {
    private val inflater = LayoutInflater.from(context)
    private val pictures = LruCache<String, Bitmap>(PICTURE_CACHE)
    private val rounded = object : ViewOutlineProvider() {
        override fun getOutline(view: View, outline: Outline) {
            outline.setRoundRect(0, 0, view.width, view.height, 10 * context.resources.displayMetrics.density)
        }
    }
    var rows: List<MediaRow> = emptyList()
        set(value) {
            field = value
            notifyDataSetChanged()
        }

    override fun getCount() = rows.size
    override fun getItem(position: Int) = rows[position]
    override fun getItemId(position: Int) = position.toLong()

    override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
        val view = convertView ?: inflater.inflate(R.layout.item_media, parent, false)
        val row = rows[position]
        view.findViewById<TextView>(R.id.rowTitle).text = row.title
        val detail = view.findViewById<TextView>(R.id.rowDetail)
        detail.text = row.detail
        detail.visibility = if (row.detail.isEmpty()) View.GONE else View.VISIBLE
        val progress = view.findViewById<ProgressBar>(R.id.rowProgress)
        progress.visibility = if (row.progress == null) View.GONE else View.VISIBLE
        progress.progress = ((row.progress ?: 0f) * progress.max).toInt()
        val image = view.findViewById<ImageView>(R.id.rowPicture)
        if (row.artUri != null) {
            Art.show(image, row.artUri, row.placeholder)
            return view
        }
        image.tag = null
        image.outlineProvider = rounded
        image.clipToOutline = true
        val bitmap = row.thumbnail?.let(::picture)
        if (bitmap != null) {
            image.imageTintList = null
            image.scaleType = ImageView.ScaleType.CENTER_CROP
            image.setImageBitmap(bitmap)
        } else {
            image.imageTintList = row.iconColour?.let(ColorStateList::valueOf) ?: android.content.res.ColorStateList.valueOf(context.themeColor(R.attr.inkMutedColor))
            image.scaleType = ImageView.ScaleType.CENTER
            image.setImageResource(row.placeholder)
        }
        return view
    }

    private fun picture(name: String): Bitmap? = pictures.get(name) ?: BitmapFactory
        .decodeFile(File(LibraryScanner.thumbnailDirectory(context), name).path)
        ?.also { pictures.put(name, it) }

    private companion object {
        const val PICTURE_CACHE = 64
    }
}
