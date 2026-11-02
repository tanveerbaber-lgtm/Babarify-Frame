package com.babarify.frame.prototype

import android.app.Activity
import android.content.Intent
import android.content.pm.ActivityInfo
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.Gravity
import android.view.SurfaceView
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import org.json.JSONArray
import org.json.JSONObject

private const val PROBE_TAG = "BabarifyProbe"
private const val REQUEST_OPEN = 1
private const val TICK_MS = 500L
private const val STATE_URI = "uri"
private const val STATE_SUBTITLE = "subtitle"
private const val STATE_POSITION = "position"
private const val STATE_PLAYING = "playing"

class MainActivity : Activity() {
    private lateinit var surface: SurfaceView
    private var engine: PlayerEngine? = null
    private var mediaUri: Uri? = null
    private var subtitleUri: Uri? = null
    private var resumeMs = 0L
    private var resumePlaying = true

    private val probe = ProbeSink { name, fields -> logProbe(name, fields) }
    private val handler = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            engine?.let {
                logProbe(
                    "tick",
                    mapOf("position_ms" to it.positionMs, "duration_ms" to it.durationMs, "playing" to it.isPlaying),
                )
            }
            handler.postDelayed(this, TICK_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        getExternalFilesDir(null) // Creates the app's own folder, where measurement runs copy media.
        surface = SurfaceView(this)
        setContentView(buildLayout())

        if (savedInstanceState != null) {
            mediaUri = savedInstanceState.getString(STATE_URI)?.let(Uri::parse)
            subtitleUri = savedInstanceState.getString(STATE_SUBTITLE)?.let(Uri::parse)
            resumeMs = savedInstanceState.getLong(STATE_POSITION)
            resumePlaying = savedInstanceState.getBoolean(STATE_PLAYING)
        } else {
            // Measurement runs: adb passes the file's location; a person uses the picker.
            mediaUri = intent.getStringExtra("media")?.let(Uri::parse)
            subtitleUri = intent.getStringExtra("subtitle")?.let(Uri::parse)
            scheduleMeasurementActions()
        }
    }

    /** Lets adb runs trigger a seek or a rotation, without changing any setting on the device. */
    private fun scheduleMeasurementActions() {
        val seekAfter = intent.getLongExtra("seek_after_ms", -1)
        val seekTo = intent.getLongExtra("seek_to_ms", 0)
        if (seekAfter >= 0) {
            handler.postDelayed({
                logProbe("seek", mapOf("to_ms" to seekTo))
                engine?.seekTo(seekTo)
            }, seekAfter)
        }
        val rotateAfter = intent.getLongExtra("rotate_after_ms", -1)
        if (rotateAfter >= 0) {
            handler.postDelayed({
                logProbe("rotate", mapOf("position_ms" to engine?.positionMs))
                requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            }, rotateAfter)
        }
    }

    override fun onStart() {
        super.onStart()
        handler.post(tick)
        val media = mediaUri ?: return
        startEngine(media)
    }

    override fun onStop() {
        handler.removeCallbacks(tick)
        // No background playback: the engine and its decoders are released with the screen.
        engine?.let {
            resumeMs = it.positionMs
            resumePlaying = it.isPlaying
            logProbe("stopped", mapOf("position_ms" to resumeMs, "was_playing" to resumePlaying))
            it.release()
        }
        engine = null
        super.onStop()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString(STATE_URI, mediaUri?.toString())
        outState.putString(STATE_SUBTITLE, subtitleUri?.toString())
        outState.putLong(STATE_POSITION, engine?.positionMs ?: resumeMs)
        outState.putBoolean(STATE_PLAYING, engine?.isPlaying ?: resumePlaying)
    }

    @Deprecated("Activity result API would add androidx.activity; the prototype stays minimal.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (requestCode != REQUEST_OPEN || resultCode != RESULT_OK || uri == null) return
        // Keeps access to this one file across restarts; nothing else becomes readable.
        contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        mediaUri = uri
        subtitleUri = null
        resumeMs = 0
        resumePlaying = true
        // Android calls onStart before delivering this result, so nothing else will open the file.
        logProbe("picked", mapOf("scheme" to uri.scheme))
        startEngine(uri)
    }

    private fun startEngine(media: Uri) {
        engine?.release()
        val created = createEngine(this, probe)
        engine = created
        created.attach(surface)
        logProbe(
            "open",
            mapOf(
                "engine" to created.name,
                "start_ms" to resumeMs,
                "clock_ms" to SystemClock.elapsedRealtime(),
            ),
        )
        created.open(media, subtitleUri, resumeMs)
        if (resumePlaying) created.play() else created.pause()
    }

    private fun buildLayout(): FrameLayout {
        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(button("Open") { openPicker() })
            addView(button("Play/Pause") { togglePlay() })
            addView(button("-10 s") { seekBy(-10_000) })
            addView(button("+10 s") { seekBy(10_000) })
        }
        // Android 15+ draws apps under the system bars; the controls must stay above them.
        controls.setOnApplyWindowInsetsListener { view, insets ->
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                view.setPadding(bars.left, 0, bars.right, bars.bottom)
            }
            insets
        }
        return FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            addView(surface, FrameLayout.LayoutParams(-1, -1, Gravity.CENTER))
            addView(controls, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL))
        }
    }

    private fun button(label: String, action: () -> Unit) = Button(this).apply {
        text = label
        setOnClickListener { action() }
    }

    private fun openPicker() {
        val pick = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("video/*", "audio/*"))
        }
        @Suppress("DEPRECATION")
        startActivityForResult(pick, REQUEST_OPEN)
    }

    private fun togglePlay() {
        val current = engine ?: return
        if (current.isPlaying) current.pause() else current.play()
    }

    private fun seekBy(deltaMs: Long) {
        val current = engine ?: return
        current.seekTo((current.positionMs + deltaMs).coerceAtLeast(0))
    }

    private fun logProbe(name: String, fields: Map<String, Any?>) {
        val json = JSONObject().put("event", name)
        for ((key, value) in fields) {
            json.put(key, if (value is List<*>) JSONArray(value) else value)
        }
        Log.i(PROBE_TAG, json.toString())
    }
}
