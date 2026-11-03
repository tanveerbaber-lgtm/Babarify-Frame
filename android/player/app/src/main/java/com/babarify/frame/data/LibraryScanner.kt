package com.babarify.frame.data

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.provider.DocumentsContract
import android.util.Log
import com.babarify.frame.core.PlaybackRules
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

/**
 * Finds media in the folders the user granted, on one background thread. Only those folders are
 * read, and files are never changed. Details and pictures wait while something is playing, so a
 * scan can't make playback stutter.
 */
class LibraryScanner(
    context: Context,
    private val store: LibraryStore,
    private val isPlaybackActive: () -> Boolean,
    private val onChanged: () -> Unit,
) {
    private val app = context.applicationContext
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val pending = AtomicInteger()

    val busy: Boolean get() = pending.get() > 0

    fun scan(folders: List<LibraryFolder> = store.folders()) {
        pending.incrementAndGet()
        worker.execute {
            try {
                for (folder in folders) scanFolder(folder)
                probePending()
                removeUnusedThumbnails()
            } catch (e: RuntimeException) {
                Log.w(TAG, "library scan stopped", e)
            } finally {
                pending.decrementAndGet()
                notifyChanged()
            }
        }
    }

    fun shutdown() {
        worker.shutdownNow()
    }

    private fun notifyChanged() {
        main.post(onChanged)
    }

    private fun scanFolder(folder: LibraryFolder) {
        val tree = Uri.parse(folder.uri)
        val found = walk(tree) ?: return // Unreachable right now: keep what we knew.
        store.replaceFolderContents(folder.id, found)
        notifyChanged()
    }

    private fun walk(tree: Uri): List<FoundFile>? {
        val found = ArrayList<FoundFile>()
        val directories = ArrayDeque<Pair<String, Int>>()
        directories.add(DocumentsContract.getTreeDocumentId(tree) to 0)
        var reachedRoot = false
        while (directories.isNotEmpty() && found.size < MAX_FILES) {
            val (directory, depth) = directories.removeFirst()
            val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, directory)
            val cursor = try {
                app.contentResolver.query(children, COLUMNS, null, null, null)
            } catch (_: SecurityException) {
                null
            } catch (_: IllegalArgumentException) {
                null
            }
            if (cursor == null) {
                if (!reachedRoot) return null
                continue
            }
            reachedRoot = true
            cursor.use { c ->
                while (c.moveToNext()) {
                    val id = c.getString(0)
                    val name = c.getString(1) ?: continue
                    if (name.startsWith(".")) continue
                    if (c.getString(2) == DocumentsContract.Document.MIME_TYPE_DIR) {
                        if (depth < MAX_DEPTH) directories.add(id to depth + 1)
                    } else if (PlaybackRules.isMediaName(name)) {
                        val uri = DocumentsContract.buildDocumentUriUsingTree(tree, id).toString()
                        val size = if (c.isNull(3)) 0 else c.getLong(3)
                        val modified = if (c.isNull(4)) 0 else c.getLong(4)
                        found.add(FoundFile(uri, name, size, modified, PlaybackRules.isVideoName(name)))
                    }
                }
            }
        }
        return found
    }

    private fun probePending() {
        var batch = store.unprobed()
        while (batch.isNotEmpty()) {
            for (entry in batch) {
                waitWhilePlaying()
                probe(entry)
            }
            notifyChanged()
            batch = store.unprobed()
        }
    }

    private fun waitWhilePlaying() {
        try {
            while (isPlaybackActive()) Thread.sleep(PLAYBACK_WAIT_MS)
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
            throw IllegalStateException("scanner shut down")
        }
    }

    /** Damaged files simply end up without details; they must not stop the scan. */
    private fun probe(entry: MediaEntry) {
        val retriever = MediaMetadataRetriever()
        var duration: Long? = null
        var thumbnail: String? = null
        try {
            retriever.setDataSource(app, Uri.parse(entry.uri))
            duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()
            if (entry.isVideo) {
                val at = (duration ?: 0L) / 10 * 1000 // A tenth of the way in usually isn't a black frame.
                retriever.getScaledFrameAtTime(at, MediaMetadataRetriever.OPTION_CLOSEST_SYNC, THUMB_WIDTH, THUMB_HEIGHT)
                    ?.let { thumbnail = saveThumbnail(entry.id, it) }
            }
        } catch (_: RuntimeException) {
            // Unreadable by the system's decoders; libVLC may still play it.
        } finally {
            try {
                retriever.release()
            } catch (_: IOException) {
                // Nothing more to do with it.
            }
        }
        store.recordProbe(entry.id, duration, thumbnail)
    }

    private fun saveThumbnail(id: Long, bitmap: Bitmap): String? {
        val directory = thumbnailDirectory(app)
        directory.mkdirs()
        val name = "$id.jpg"
        return try {
            FileOutputStream(File(directory, name)).use { bitmap.compress(Bitmap.CompressFormat.JPEG, 80, it) }
            name
        } catch (_: IOException) {
            null
        } finally {
            bitmap.recycle()
        }
    }

    private fun removeUnusedThumbnails() {
        val used = store.thumbnails()
        thumbnailDirectory(app).listFiles()?.forEach { if (it.name !in used) it.delete() }
    }

    companion object {
        private const val TAG = "BabarifyLibrary"
        private const val MAX_FILES = 50_000
        private const val MAX_DEPTH = 20
        private const val PLAYBACK_WAIT_MS = 1_000L
        private const val THUMB_WIDTH = 240
        private const val THUMB_HEIGHT = 135
        private val COLUMNS = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE,
            DocumentsContract.Document.COLUMN_LAST_MODIFIED,
        )

        fun thumbnailDirectory(context: Context) = File(context.applicationContext.filesDir, "thumbnails")
    }
}
