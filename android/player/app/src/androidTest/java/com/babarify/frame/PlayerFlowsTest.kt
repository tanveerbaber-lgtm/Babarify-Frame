package com.babarify.frame

import android.app.Activity
import android.app.Instrumentation
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.graphics.Rect
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import android.view.WindowInsets
import android.view.View
import android.widget.Button
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.babarify.frame.engine.PlaybackSession
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.core.TrackKind
import com.babarify.frame.data.HistoryEntry
import com.babarify.frame.data.HistoryStore
import com.babarify.frame.ui.HomeActivity
import com.babarify.frame.ui.PlayerActivity
import androidx.lifecycle.Lifecycle
import java.io.File
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PlayerFlowsTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private lateinit var history: HistoryStore

    @Before
    fun clearHistory() {
        // Audio from an earlier test may still be playing on, as it does for users.
        instrumentation.runOnMainSync { com.babarify.frame.engine.PlaybackSession.get(context).clearMedia() }
        com.babarify.frame.engine.BackgroundPlaybackService.stop(context)
        history = HistoryStore(context)
        history.clear()
        if (!fontCache().exists()) {
            // Other tests expect normal opening speed, so build libVLC's font cache first.
            open("s_sidecar_720p.mp4").use { scenario ->
                waitUntil("font cache built", 180_000) { scenario.read { it.playbackState } == PlaybackState.PLAYING }
            }
        }
    }

    private fun fontCache() = File(context.getDir("vlc", Context.MODE_PRIVATE), ".cache/fontconfig")

    @After
    fun closeHistory() = history.close()

    private fun playerIntent(uri: Uri) =
        Intent(context, PlayerActivity::class.java).setData(uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    private fun open(name: String) = ActivityScenario.launch<PlayerActivity>(playerIntent(TestMediaProvider.uri(name)))

    private fun waitUntil(what: String, timeoutMs: Long = 20_000, condition: () -> Boolean) {
        val end = SystemClock.elapsedRealtime() + timeoutMs
        while (SystemClock.elapsedRealtime() < end) {
            if (condition()) return
            SystemClock.sleep(100)
        }
        throw AssertionError("timed out waiting: $what")
    }

    private fun <T> ActivityScenario<PlayerActivity>.read(block: (PlayerActivity) -> T): T {
        var result: T? = null
        onActivity { result = block(it) }
        @Suppress("UNCHECKED_CAST")
        return result as T
    }

    /** Asks the main thread directly: onActivity first waits for it to go idle, which moving bars can delay past a clip's end. */
    private fun positionNow(): Long {
        var position = 0L
        InstrumentationRegistry.getInstrumentation().runOnMainSync { position = PlaybackSession.get(InstrumentationRegistry.getInstrumentation().targetContext).positionMs }
        return position
    }

    private fun ActivityScenario<PlayerActivity>.waitForProgress(aboveMs: Long = 500) =
        waitUntil("position above $aboveMs") { positionNow() > aboveMs }

    // M12 finding 2: Android delivers the picker's result after onStart, and the file was ignored.
    @Test
    fun aFilePickedFromHomeStartsPlaying() {
        var pickerOpened = false
        val picker = object : Instrumentation.ActivityMonitor() {
            override fun onStartActivity(intent: Intent): Instrumentation.ActivityResult? {
                if (intent.action != Intent.ACTION_OPEN_DOCUMENT) return null
                pickerOpened = true
                val picked = Intent().setData(TestMediaProvider.uri("s_sidecar_720p.mp4"))
                return Instrumentation.ActivityResult(Activity.RESULT_OK, picked)
            }
        }
        instrumentation.addMonitor(picker)
        val player = instrumentation.addMonitor(PlayerActivity::class.java.name, null, false)
        try {
            ActivityScenario.launch(HomeActivity::class.java).use { home ->
                home.onActivity { it.findViewById<Button>(R.id.openButton).performClick() }
                val activity = instrumentation.waitForMonitorWithTimeout(player, 15_000) as PlayerActivity?
                assertNotNull("the picked file never reached the player", activity)
                waitUntil("picked file playing") { activity!!.currentPositionMs > 500 }
                assertTrue(pickerOpened)
                activity!!.finish()
            }
        } finally {
            instrumentation.removeMonitor(picker)
            instrumentation.removeMonitor(player)
        }
    }

    // M12 finding 1: the prototype's buttons sat under the navigation bar.
    @Test
    fun controlsStayClearOfTheSystemBars() {
        open("s_sidecar_720p.mp4").use { scenario ->
            for (orientation in listOf(
                ActivityInfo.SCREEN_ORIENTATION_PORTRAIT,
                ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE,
            )) {
                scenario.onActivity { it.requestedOrientation = orientation }
                SystemClock.sleep(1_500)
                scenario.onActivity { it.showControls() }
                SystemClock.sleep(300)
                scenario.onActivity { activity ->
                    val root = activity.window.decorView
                    val safe = safeArea(root)
                    for (id in listOf(R.id.closeButton, R.id.moreButton, R.id.playButton, R.id.backButton, R.id.subtitleButton, R.id.volumeButton, R.id.rotateButton)) {
                        val location = IntArray(2)
                        val button = activity.findViewById<android.view.View>(id)
                        button.getLocationInWindow(location)
                        val box = Rect(location[0], location[1], location[0] + button.width, location[1] + button.height)
                        assertTrue("$orientation: $box outside $safe", safe.contains(box))
                    }
                }
            }
        }
    }

    private fun safeArea(root: android.view.View): Rect {
        val insets = root.rootWindowInsets
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bars = insets.getInsets(WindowInsets.Type.systemBars())
            Rect(bars.left, bars.top, root.width - bars.right, root.height - bars.bottom)
        } else {
            @Suppress("DEPRECATION")
            Rect(
                insets.systemWindowInsetLeft,
                insets.systemWindowInsetTop,
                root.width - insets.systemWindowInsetRight,
                root.height - insets.systemWindowInsetBottom,
            )
        }
    }

    @Test
    fun damagedAndUnreadableFilesShowAMessage() {
        for (name in listOf("truncated.mp4", "not_media.mp4", "e_empty.mp4", TestMediaProvider.MISSING)) {
            open(name).use { scenario ->
                waitUntil("message for $name") { scenario.read { it.visibleMessage } != null }
                val label = scenario.read { it.findViewById<View>(R.id.playButton).contentDescription.toString() }
                assertEquals(context.getString(R.string.play), label)
            }
        }
    }

    @Test
    fun otherAddressTypesAreRefused() {
        val refused = Uri.parse("file:///sdcard/Download/a.mp4")
        ActivityScenario.launch<PlayerActivity>(playerIntent(refused)).use { scenario ->
            assertNotNull(scenario.read { it.visibleMessage })
            assertNull(scenario.read { it.playbackState })
        }
    }

    @Test
    fun audioOnlyFilesAdvance() {
        // M12 finding 4: Ogg audio did not advance in one libVLC run, without an explanation.
        for (name in listOf("c_audio_aac.m4a", "c_audio_opus.opus", "c_audio_vorbis.ogg")) {
            repeat(3) {
                open(name).use { it.waitForProgress() }
            }
        }
    }

    @Test
    fun rotationKeepsTheSameEngineAndPosition() {
        open("s_sidecar_720p.mp4").use { scenario ->
            scenario.waitForProgress()
            val engine = scenario.read { it.engineInstance }
            val before = scenario.read { it.currentPositionMs }
            scenario.onActivity { it.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE }
            SystemClock.sleep(1_000)
            assertSame(engine, scenario.read { it.engineInstance })
            assertTrue(scenario.read { it.currentPositionMs } >= before)
        }
    }

    // M13: on a new install libVLC scans the phone's fonts first, about 22 s on a Galaxy A33. This
    // must look like preparing, never like "could not be played", and must not freeze the screen.
    @Test
    fun theFirstFileShowsPreparingThenPlays() {
        fontCache().parentFile!!.deleteRecursively()
        open("s_sidecar_720p.mp4").use { scenario ->
            waitUntil("playing", 180_000) {
                val message = scenario.read { it.visibleMessage }?.toString()
                assertFalse(message, message == context.getString(R.string.error_media_open_failed))
                scenario.read { it.playbackState } == PlaybackState.PLAYING
            }
            assertNull(scenario.read { it.visibleMessage })
        }
    }

    @Test
    fun leavingDuringTheFirstFileDoesNotFreezeTheScreen() {
        fontCache().parentFile!!.deleteRecursively()
        val scenario = open("s_sidecar_720p.mp4")
        SystemClock.sleep(3_000)
        val state = scenario.read { it.playbackState }
        val before = SystemClock.elapsedRealtime()
        scenario.close()
        val took = SystemClock.elapsedRealtime() - before
        // A fast device may already be playing, where the normal path applies.
        if (state == PlaybackState.LOADING) assertTrue("closing took $took ms", took < 5_000)
    }

    @Test
    fun aFinishedFileComesBackAtItsStart() {
        open("c_audio_aac.m4a").use { scenario ->
            waitUntil("file finished") { scenario.read { it.playbackState } == PlaybackState.ENDED }
            scenario.moveToState(Lifecycle.State.CREATED)
            scenario.moveToState(Lifecycle.State.RESUMED)
            SystemClock.sleep(1_000)
            assertTrue(scenario.read { it.currentPositionMs } < 1_000)
            assertFalse(scenario.read { it.playbackState } == PlaybackState.PLAYING)
        }
    }

    @Test
    fun leavingReleasesTheEngineAndReturningContinues() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress(2_000)
            scenario.moveToState(Lifecycle.State.CREATED)
            assertNull("nothing may play while away", scenario.read { it.playbackState })
            val left = scenario.read { it.currentPositionMs }
            assertTrue(left >= 2_000)
            scenario.moveToState(Lifecycle.State.RESUMED)
            waitUntil("playing again") { scenario.read { it.playbackState } == PlaybackState.PLAYING }
            assertTrue(scenario.read { it.currentPositionMs } >= left - 1_000)
        }
    }

    @Test
    fun aPausedFileStaysPausedAfterReturning() {
        open("s_sidecar_720p.mp4").use { scenario ->
            scenario.waitForProgress()
            scenario.onActivity { it.findViewById<View>(R.id.playButton).performClick() }
            waitUntil("paused") { scenario.read { it.playbackState } == PlaybackState.PAUSED }
            scenario.moveToState(Lifecycle.State.CREATED)
            scenario.moveToState(Lifecycle.State.RESUMED)
            SystemClock.sleep(2_000)
            assertFalse(scenario.read { it.playbackState } == PlaybackState.PLAYING)
        }
    }

    @Test
    fun seekButtonsMoveThePosition() {
        open("s_sidecar_720p.mp4").use { scenario ->
            scenario.waitForProgress()
            scenario.onActivity { it.findViewById<View>(R.id.forwardButton).performClick() }
            waitUntil("position moved forward", 5_000) { scenario.read { it.currentPositionMs } > 5_000 }
        }
    }

    @Test
    fun tracksAreListedAndCanBeChosen() {
        open("s_black_tracks_720p.mkv").use { scenario ->
            waitUntil("audio tracks") { scenario.read { it.tracksOf(TrackKind.AUDIO) }.size >= 2 }
            val audio = scenario.read { it.tracksOf(TrackKind.AUDIO) }.last { !it.selected && it.id >= 0 }
            scenario.onActivity { it.selectTrack(TrackKind.AUDIO, audio.id) }
            waitUntil("audio track selected", 5_000) {
                scenario.read { it.tracksOf(TrackKind.AUDIO) }.first { it.id == audio.id }.selected
            }
            assertTrue(scenario.read { it.tracksOf(TrackKind.SUBTITLE) }.isNotEmpty())
        }
    }

    @Test
    fun aPickedSubtitleFileBecomesATrack() {
        open("s_sidecar_720p.mp4").use { scenario ->
            scenario.waitForProgress()
            val before = scenario.read { it.tracksOf(TrackKind.SUBTITLE) }.size
            scenario.onActivity { it.addSubtitle(TestMediaProvider.uri("s_ext.srt")) }
            waitUntil("subtitle track", 8_000) { scenario.read { it.tracksOf(TrackKind.SUBTITLE) }.size > before }
        }
    }

    @Test
    fun playingAddsToRecentAndResumes() {
        val uri = TestMediaProvider.uri("s_sidecar_720p.mp4")
        history.save(HistoryEntry(uri.toString(), "saved", 6_000, 10_000, false))
        open("s_sidecar_720p.mp4").use { scenario ->
            waitUntil("playing from the saved place") { scenario.read { it.currentPositionMs } >= 5_500 }
        }
        val saved = history.find(uri.toString())
        assertNotNull(saved)
        assertEquals("s_sidecar_720p.mp4", saved!!.title)
    }

    @Test
    fun aDamagedFileIsNotAddedToRecent() {
        open("not_media.mp4").use { scenario ->
            waitUntil("message") { scenario.read { it.visibleMessage } != null }
        }
        assertNull(history.find(TestMediaProvider.uri("not_media.mp4").toString()))
    }

    @Test
    fun theAppHasOnlyTheAgreedPermissions() {
        val info = context.packageManager.getPackageInfo(
            context.packageName,
            android.content.pm.PackageManager.GET_PERMISSIONS,
        )
        // Sound that keeps playing, and reading songs once the user allows it. Never the internet.
        val expected = mutableSetOf(
            "android.permission.FOREGROUND_SERVICE",
            "android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK",
            "android.permission.WAKE_LOCK",
            "android.permission.READ_MEDIA_AUDIO",
        )
        // Android 13 and later ignore this older, wider one, because the manifest limits it to before them.
        if (android.os.Build.VERSION.SDK_INT <= android.os.Build.VERSION_CODES.S_V2) {
            expected += "android.permission.READ_EXTERNAL_STORAGE"
        }
        assertEquals(expected.toSet(), info.requestedPermissions.orEmpty().toSet())
    }

    @Test
    fun licencesAreShipped() {
        for (name in listOf("THIRD_PARTY_NOTICES.txt", "GPL-3.0.txt", "LGPL-2.1.txt", "Apache-2.0.txt")) {
            assertTrue(name, context.assets.open("licenses/$name").bufferedReader().use { it.readText() }.length > 100)
        }
    }
}
