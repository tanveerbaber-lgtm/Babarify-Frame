package com.babarify.frame

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.SystemClock
import android.provider.DocumentsContract
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.babarify.frame.core.LeaveAction
import com.babarify.frame.core.PictureSettings
import com.babarify.frame.core.PlaybackState
import com.babarify.frame.core.SortOrder
import com.babarify.frame.core.SubtitleStyle
import com.babarify.frame.core.TrackKind
import com.babarify.frame.core.VideoTransform
import com.babarify.frame.data.HistoryStore
import com.babarify.frame.data.LibraryStore
import com.babarify.frame.data.Preferences
import com.babarify.frame.engine.PlaybackSession
import com.babarify.frame.ui.HomeActivity
import com.babarify.frame.ui.LibraryActivity
import com.babarify.frame.ui.PlayerActivity
import com.babarify.frame.ui.PlaylistActivity
import com.babarify.frame.ui.PlaylistsActivity
import com.babarify.frame.ui.SettingsActivity
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Features added to match the desktop app. Everything runs against real libVLC playback. */
@RunWith(AndroidJUnit4::class)
class FeatureFlowsTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private lateinit var preferences: Preferences
    private lateinit var library: LibraryStore
    private lateinit var history: HistoryStore

    @Before
    fun setUp() {
        preferences = Preferences(context)
        preferences.resetToDefaults()
        session().setVolumeLevel(100)
        library = LibraryStore(context)
        history = HistoryStore(context)
        history.clear()
        clearLibrary()
    }

    @After
    fun tearDown() {
        clearLibrary()
        library.close()
        history.close()
        preferences.resetToDefaults()
    }

    private fun clearLibrary() {
        library.folders().forEach { library.removeFolder(it.id) }
        library.playlists().forEach { library.deletePlaylist(it.id) }
    }

    private fun session() = PlaybackSession.get(context)

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

    private fun <A : android.app.Activity, T> ActivityScenario<A>.read(block: (A) -> T): T {
        var result: T? = null
        onActivity { result = block(it) }
        @Suppress("UNCHECKED_CAST")
        return result as T
    }

    private fun ActivityScenario<PlayerActivity>.waitForProgress(aboveMs: Long = 500) =
        waitUntil("position above $aboveMs", 180_000) { read { it.currentPositionMs } > aboveMs }

    /** What's really on screen, which includes colour filters and view rotation. */
    private fun screen(): Bitmap = instrumentation.uiAutomation.takeScreenshot()

    private fun averageBrightness(bitmap: Bitmap): Double {
        var sum = 0L
        var count = 0L
        for (y in bitmap.height / 4 until bitmap.height / 2 step 8) {
            for (x in bitmap.width / 8 until bitmap.width * 7 / 8 step 8) {
                val pixel = bitmap.getPixel(x, y)
                sum += Color.red(pixel) + Color.green(pixel) + Color.blue(pixel)
                count += 3
            }
        }
        return sum.toDouble() / count
    }

    private fun ActivityScenario<PlayerActivity>.hideControls() {
        onActivity { it.controlsView.visibility = View.GONE }
    }

    private fun frame(scenario: ActivityScenario<PlayerActivity>): Bitmap? = scenario.read { it.videoView.bitmap }

    private fun hasPicture(bitmap: Bitmap?): Boolean {
        bitmap ?: return false
        return averageBrightness(bitmap) > 5
    }

    // ------------------------------------------------------ volume and speed
    @Test
    fun normalVolumeRunsFrom1To100AndBoostTo200() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            val session = session()
            session.setVolumeLevel(0)
            assertEquals(1, session.volume)
            session.setVolumeLevel(150)
            assertEquals(100, session.volume)
            waitUntil("engine at 100", 5_000) { session.engine!!.volume == 100 }

            preferences.allowVolumeBoost = true
            scenario.onActivity { session.setVolumeLevel(200) }
            assertEquals(200, session.volume)
            waitUntil("engine at 200", 5_000) { session.engine!!.volume == 200 }
            assertEquals("a boost is never remembered", 100, preferences.volume)

            preferences.allowVolumeBoost = false
            scenario.onActivity { session.onPreferencesChanged() }
            assertEquals(100, session.volume)
        }
    }

    @Test
    fun theVolumeNumberIsShownOnTheButton() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            val label = scenario.read { it.findViewById<Button>(R.id.volumeButton).text.toString() }
            assertEquals("100", label)
        }
    }

    @Test
    fun speedChangesHowFastThePositionMoves() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            scenario.onActivity { it.setRate(2f) }
            assertEquals(2f, session().rate)
            val before = scenario.read { it.currentPositionMs }
            SystemClock.sleep(3_000)
            val moved = scenario.read { it.currentPositionMs } - before
            assertTrue("moved $moved ms in 3 s at 2x", moved > 4_000)
            val label = scenario.read { it.findViewById<Button>(R.id.speedButton).text.toString() }
            assertEquals("2×", label)
        }
    }

    // --------------------------------------------------- picture and geometry
    @Test
    fun brightnessFilterChangesWhatIsOnScreen() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress(1_000)
            scenario.hideControls()
            waitUntil("picture on screen", 10_000) { averageBrightness(screen()) > 10 }
            val normal = averageBrightness(screen())
            preferences.picture = PictureSettings(brightness = 0f)
            scenario.onActivity { it.applyPicture() }
            SystemClock.sleep(800)
            val dark = averageBrightness(screen())
            assertTrue("normal $normal, dark $dark", dark < normal / 2)
            preferences.picture = PictureSettings()
            scenario.onActivity { it.applyPicture() }
        }
    }

    @Test
    fun rotationKeepsVideoInsideTheView() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            scenario.onActivity { it.setTransform(VideoTransform.ROTATE_90) }
            val view = scenario.read { it.videoView }
            assertEquals(90f, view.rotation)
            assertTrue(view.scaleX < 1f)
            scenario.onActivity { it.setTransform(VideoTransform.FLIP_HORIZONTAL) }
            assertEquals(0f, view.rotation)
            assertTrue(view.scaleX < 0f)
        }
    }

    @Test
    fun aSnapshotIsSavedAndReadable() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress(1_000)
            scenario.onActivity { it.takeSnapshot() }
            waitUntil("snapshot saved", 10_000) { scenario.read { it.lastSnapshot } != null }
            val uri = scenario.read { it.lastSnapshot }!!
            try {
                val bytes = context.contentResolver.openInputStream(uri)!!.use { it.readBytes() }
                assertTrue(bytes.size > 1_000)
            } finally {
                context.contentResolver.delete(uri, null, null)
            }
        }
    }

    // ---------------------------------------------------------------- sound
    @Test
    fun equalizerPresetsExistAndApply() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            val engine = session().engine!!
            val names = engine.equalizerPresets()
            assertTrue(names.size > 5)
            val preset = engine.equalizerPreset(names.indexOf("Rock").coerceAtLeast(0))
            assertTrue(preset.enabled)
            assertEquals(10, engine.equalizerBandFrequencies().size)
            scenario.onActivity { engine.setEqualizer(preset) }
            val before = scenario.read { it.currentPositionMs }
            waitUntil("still playing") { scenario.read { it.currentPositionMs } > before + 500 }
        }
    }

    @Test
    fun audioAndSubtitleDelaysAreKeptAcrossLeaving() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            scenario.onActivity {
                session().setAudioDelay(150)
                session().setSubtitleDelay(-300)
            }
            scenario.moveToState(Lifecycle.State.CREATED)
            scenario.moveToState(Lifecycle.State.RESUMED)
            scenario.waitForProgress()
            assertEquals(150, session().audioDelayMs)
            assertEquals(-300, session().subtitleDelayMs)
        }
    }

    // ------------------------------------------------------------ navigation
    @Test
    fun abRepeatJumpsBack() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress(2_000)
            scenario.onActivity { it.pressAbRepeat() }
            val a = session().abLoop.a!!
            SystemClock.sleep(1_500)
            scenario.onActivity { it.pressAbRepeat() }
            val b = session().abLoop.b!!
            assertTrue(b > a)
            var sawJump = false
            val end = SystemClock.elapsedRealtime() + 8_000
            var last = scenario.read { it.currentPositionMs }
            while (SystemClock.elapsedRealtime() < end) {
                SystemClock.sleep(100)
                val now = scenario.read { it.currentPositionMs }
                if (now < last - 500) sawJump = true
                last = now
            }
            assertTrue("never jumped back", sawJump)
            assertTrue("ran past B: $last, B $b", last < b + 2_000)
            scenario.onActivity { it.pressAbRepeat() }
            assertNull(session().abLoop.a)
        }
    }

    @Test
    fun chaptersAreListedAndNextChapterSeeks() {
        open("chapters_30s.mkv").use { scenario ->
            scenario.waitForProgress()
            waitUntil("chapters") { scenario.read { session().chapters() }.size == 3 }
            val chapters = scenario.read { session().chapters() }
            assertEquals(listOf(0L, 10_000L, 20_000L), chapters.map { it.startMs })
            assertEquals("Second part", chapters[1].title)
            scenario.onActivity { session().nextChapter() }
            waitUntil("in the second chapter", 5_000) { scenario.read { it.currentPositionMs } >= 10_000 }
        }
    }

    @Test
    fun bookmarksArePerFile() {
        val uri = TestMediaProvider.uri("long_60s.mp4").toString()
        val id = library.addBookmark(uri, 12_000, "Good part")
        try {
            assertEquals(listOf("Good part"), library.bookmarks(uri).map { it.label })
            assertTrue(library.bookmarks(TestMediaProvider.uri("other.mp4").toString()).isEmpty())
        } finally {
            library.removeBookmark(id)
        }
        assertTrue(library.bookmarks(uri).isEmpty())
    }

    @Test
    fun aPlaylistMovesOnAndNextPreviousWork() {
        val items = listOf("long_60s.mp4", "c_audio_aac.m4a", "s_sidecar_720p.mp4")
        val intent = playerIntent(TestMediaProvider.uri(items[0]))
            .putStringArrayListExtra(PlayerActivity.EXTRA_QUEUE_URIS, ArrayList(items.map { TestMediaProvider.uri(it).toString() }))
            .putStringArrayListExtra(PlayerActivity.EXTRA_QUEUE_TITLES, ArrayList(items))
            .putExtra(PlayerActivity.EXTRA_QUEUE_INDEX, 0)
        ActivityScenario.launch<PlayerActivity>(intent).use { scenario ->
            scenario.waitForProgress()
            scenario.onActivity { it.findViewById<View>(R.id.nextButton).performClick() }
            waitUntil("second file") { session().title == items[1] }
            // The audio clip is short: at its end, the third file starts by itself.
            waitUntil("third file", 60_000) { session().title == items[2] }
            waitUntil("third file plays") { scenario.read { it.playbackState } == PlaybackState.PLAYING }
            val label = scenario.read { it.findViewById<android.widget.TextView>(R.id.titleLabel).text.toString() }
            assertEquals(items[2], label)
            assertFalse(session().queue.hasNext)
            assertFalse(scenario.read { it.findViewById<View>(R.id.nextButton).isEnabled })
        }
    }

    // ------------------------------------------------- leaving the player
    @Test
    fun soundKeepsPlayingWhenAskedAndTheVideoComesBack() {
        preferences.leaveAction = LeaveAction.AUDIO
        val manager = context.getSystemService(NotificationManager::class.java)
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress(1_000)
            waitUntil("notification shown", 5_000) { manager.activeNotifications.isNotEmpty() }
            val engine = scenario.read { it.engineInstance }
            scenario.moveToState(Lifecycle.State.CREATED)
            assertSame(engine, session().engine)
            assertEquals(PlaybackState.PLAYING, session().state)
            val away = session().positionMs
            waitUntil("position moves while away", 8_000) { session().positionMs > away + 1_500 }

            scenario.moveToState(Lifecycle.State.RESUMED)
            assertSame(engine, scenario.read { it.engineInstance })
            waitUntil("picture returns", 15_000) { hasPicture(frame(scenario)) }
            val back = scenario.read { it.currentPositionMs }
            waitUntil("still playing") { scenario.read { it.currentPositionMs } > back + 500 }
        }
        waitUntil("notification gone after closing", 5_000) { manager.activeNotifications.isEmpty() }
        assertNull("closing the player stops the sound", session().engine)
    }

    @Test
    fun byDefaultNothingRunsInTheBackground() {
        val manager = context.getSystemService(NotificationManager::class.java)
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress(1_000)
            assertTrue(manager.activeNotifications.isEmpty())
            scenario.moveToState(Lifecycle.State.CREATED)
            assertNull(session().engine)
        }
    }

    @Test
    fun theSmallWindowKeepsPlaying() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress(1_000)
            waitUntil("video size known") { scenario.read { session().engine?.videoSize } != null }
            val entered = scenario.read { it.enterPicture() }
            assertTrue(entered)
            waitUntil("in the small window", 5_000) { scenario.read { it.isInPictureInPictureMode } }
            val before = scenario.read { it.currentPositionMs }
            waitUntil("still playing") { scenario.read { it.currentPositionMs } > before + 1_000 }
            waitUntil("controls hidden", 2_000) { scenario.read { it.controlsView.visibility } == View.GONE }
        }
    }

    // ------------------------------------------------------------- gestures
    private fun swipe(scenario: ActivityScenario<PlayerActivity>, fromX: Float, fromY: Float, toX: Float, toY: Float) {
        scenario.onActivity { activity ->
            val layer = activity.findViewById<View>(R.id.gestureLayer)
            val start = SystemClock.uptimeMillis()
            val x0 = layer.width * fromX
            val y0 = layer.height * fromY
            val x1 = layer.width * toX
            val y1 = layer.height * toY
            fun send(action: Int, at: Long, x: Float, y: Float) {
                val event = MotionEvent.obtain(start, start + at, action, x, y, 0)
                layer.dispatchTouchEvent(event)
                event.recycle()
            }
            send(MotionEvent.ACTION_DOWN, 0, x0, y0)
            for (i in 1..10) send(MotionEvent.ACTION_MOVE, i * 20L, x0 + (x1 - x0) * i / 10, y0 + (y1 - y0) * i / 10)
            send(MotionEvent.ACTION_UP, 220, x1, y1)
        }
    }

    @Test
    fun swipingChangesVolumeAndPosition() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            scenario.onActivity { session().setVolumeLevel(50) }
            swipe(scenario, 0.8f, 0.7f, 0.8f, 0.3f)
            assertTrue("volume ${session().volume}", session().volume > 60)

            val before = scenario.read { it.currentPositionMs }
            swipe(scenario, 0.3f, 0.5f, 0.7f, 0.5f)
            waitUntil("seeked", 5_000) { scenario.read { it.currentPositionMs } > before + 20_000 }
        }
    }

    @Test
    fun gesturesCanBeTurnedOff() {
        preferences.gestures = false
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            scenario.onActivity { session().setVolumeLevel(50) }
            swipe(scenario, 0.8f, 0.7f, 0.8f, 0.3f)
            assertEquals(50, session().volume)
        }
    }

    // ---------------------------------------------------- tracks and subtitles
    @Test
    fun preferredLanguageIsChosenWhenAFileOpens() {
        open("s_black_tracks_720p.mkv").use { scenario ->
            waitUntil("tracks") { scenario.read { it.tracksOf(TrackKind.AUDIO) }.size >= 3 }
            val second = scenario.read { it.tracksOf(TrackKind.AUDIO) }
            val language = second.firstNotNullOfOrNull { track ->
                com.babarify.frame.core.PlaybackRules.LANGUAGES.keys.firstOrNull {
                    !track.selected && track.id >= 0 && com.babarify.frame.core.PlaybackRules.languageMatches(it, track.title)
                }
            }
            assertNotNull("the clip needs a second language: $second", language)
            preferences.preferredAudioLanguage = language!!
        }
        open("s_black_tracks_720p.mkv").use { scenario ->
            waitUntil("preferred track selected", 10_000) {
                scenario.read { it.tracksOf(TrackKind.AUDIO) }.any { it.selected && com.babarify.frame.core.PlaybackRules.languageMatches(preferences.preferredAudioLanguage, it.title) }
            }
        }
    }

    @Test
    fun aChosenTrackSurvivesLeavingAndReturning() {
        open("s_black_tracks_720p.mkv").use { scenario ->
            waitUntil("tracks") { scenario.read { it.tracksOf(TrackKind.AUDIO) }.size >= 3 }
            val track = scenario.read { it.tracksOf(TrackKind.AUDIO) }.last { !it.selected && it.id >= 0 }
            scenario.onActivity { it.selectTrack(TrackKind.AUDIO, track.id) }
            scenario.moveToState(Lifecycle.State.CREATED)
            scenario.moveToState(Lifecycle.State.RESUMED)
            waitUntil("same track again", 15_000) {
                scenario.read { it.tracksOf(TrackKind.AUDIO) }.firstOrNull { it.id == track.id }?.selected == true
            }
        }
    }

    @Test
    fun subtitleLookChangesTheColourOnScreen() {
        preferences.subtitleStyle = SubtitleStyle(sizePct = 200, textColor = 0xFFFF00)
        open("s_black_tracks_720p.mkv").use { scenario ->
            scenario.waitForProgress()
            scenario.hideControls()
            waitUntil("embedded tracks", 8_000) { scenario.read { it.tracksOf(TrackKind.SUBTITLE) }.size >= 3 }
            val embedded = scenario.read { it.tracksOf(TrackKind.SUBTITLE) }.size
            scenario.onActivity { it.addSubtitle(TestMediaProvider.uri("s_ext.srt")) }
            waitUntil("subtitle track", 8_000) { scenario.read { it.tracksOf(TrackKind.SUBTITLE) }.size > embedded }
            val yellow = scenario.read { activity -> activity.tracksOf(TrackKind.SUBTITLE).last() }
            scenario.onActivity { it.selectTrack(TrackKind.SUBTITLE, yellow.id) }
            waitUntil("yellow text on screen", 25_000) {
                val shot = screen()
                var found = 0
                for (y in 0 until shot.height step 4) {
                    for (x in 0 until shot.width step 4) {
                        val p = shot.getPixel(x, y)
                        if (Color.red(p) > 200 && Color.green(p) > 200 && Color.blue(p) < 80) found++
                    }
                }
                found > 5
            }
        }
    }

    // -------------------------------------------------------------- library
    @Test
    fun aFolderIsScannedWithoutReadingAnythingElse() {
        ActivityScenario.launch(LibraryActivity::class.java).use { scenario ->
            scenario.onActivity { it.addFolder(TestMediaProvider.tree()) }
            waitUntil("files found", 60_000) { scenario.read { it.shownEntries }.size == 4 }
            val names = scenario.read { it.shownEntries }.map { it.name }
            // Media from the folder and its subfolder. Not the hidden file or the subtitle.
            assertEquals(setOf("long_60s.mp4", "c_audio_aac.m4a", "not_media.mp4", "s_sidecar_720p.mp4"), names.toSet())

            waitUntil("details read", 120_000) { !scenario.read { it.scanning } }
            scenario.onActivity { it.setSearch("") }
            val entries = scenario.read { it.shownEntries }
            val long = entries.first { it.name == "long_60s.mp4" }
            assertTrue("length ${long.durationMs}", (long.durationMs ?: 0) in 55_000..65_000)
            assertNotNull("a video gets a picture", long.thumbnail)
            val damaged = entries.first { it.name == "not_media.mp4" }
            assertTrue("a damaged file doesn't stop the scan", damaged.probed)
            assertNull(damaged.durationMs)

            scenario.onActivity { it.setSearch("sidecar") }
            assertEquals(listOf("s_sidecar_720p.mp4"), scenario.read { it.shownEntries }.map { it.name })
            scenario.onActivity { it.setSearch("100%") }
            assertTrue(scenario.read { it.shownEntries }.isEmpty())
        }
    }

    @Test
    fun aLibraryFilePlaysThroughItsFolderAddress() {
        val document = DocumentsContract.buildDocumentUriUsingTree(TestMediaProvider.tree(), "long_60s.mp4")
        ActivityScenario.launch<PlayerActivity>(playerIntent(document)).use { scenario ->
            scenario.waitForProgress()
        }
    }

    @Test
    fun libraryKnowsSortsAndForgetsWithTheFolder() {
        val folder = library.addFolder("content://test/tree/a", "A")
        library.replaceFolderContents(
            folder,
            listOf(
                com.babarify.frame.data.FoundFile("content://test/b", "b.mp4", 5, 1, true),
                com.babarify.frame.data.FoundFile("content://test/a", "a.mp3", 9, 1, false),
            ),
            now = 10,
        )
        assertEquals(listOf("a.mp3", "b.mp4"), library.media().map { it.name })
        assertEquals(listOf("a.mp3", "b.mp4"), library.media(sort = SortOrder.SIZE).map { it.name })
        val recent = mapOf("content://test/b" to 100L)
        assertEquals(listOf("b.mp4", "a.mp3"), library.media(sort = SortOrder.RECENTLY_PLAYED, recent = recent).map { it.name })

        library.recordProbe(library.media().first().id, 1234, null)
        library.replaceFolderContents(folder, listOf(com.babarify.frame.data.FoundFile("content://test/a", "a.mp3", 9, 1, false)), now = 20)
        val kept = library.media().single()
        assertEquals("details survive another scan", 1234L, kept.durationMs)
        library.removeFolder(folder)
        assertTrue(library.media().isEmpty())
    }

    @Test
    fun playlistsKeepOrder() {
        val id = library.createPlaylist("Road trip")
        library.addToPlaylist(id, "content://x/1", "one")
        library.addToPlaylist(id, "content://x/2", "two")
        library.addToPlaylist(id, "content://x/3", "three")
        val items = library.playlistItems(id)
        assertEquals(listOf("one", "two", "three"), items.map { it.title })
        library.moveInPlaylist(items[2], -1)
        assertEquals(listOf("one", "three", "two"), library.playlistItems(id).map { it.title })
        library.moveInPlaylist(library.playlistItems(id)[0], -1)
        assertEquals("one", library.playlistItems(id)[0].title)
        library.removePlaylistItem(library.playlistItems(id)[1])
        assertEquals(listOf("one", "two"), library.playlistItems(id).map { it.title })
        assertEquals(2, library.playlists().single().itemCount)
        library.deletePlaylist(id)
        assertTrue(library.playlists().isEmpty())
    }

    // ------------------------------------------------------------- settings
    @Test
    fun settingsSurviveAndUnreadableOnesFallBack() {
        preferences.seekStepSeconds = 30
        preferences.picture = PictureSettings(brightness = 1.5f)
        preferences.subtitleStyle = SubtitleStyle(150, 0xFFFF00, 40)
        preferences.leaveAction = LeaveAction.AUDIO
        val fresh = Preferences(context)
        assertEquals(30, fresh.seekStepSeconds)
        assertEquals(1.5f, fresh.picture.brightness)
        assertEquals(SubtitleStyle(150, 0xFFFF00, 40), fresh.subtitleStyle)
        assertEquals(LeaveAction.AUDIO, fresh.leaveAction)

        val raw = context.getSharedPreferences("preferences", Context.MODE_PRIVATE)
        raw.edit()
            .putString("picture", "{broken")
            .putString("leave_action", "NONSENSE")
            .putInt("seek_step_s", 7)
            .putString("profiles", "not a list")
            .apply()
        assertEquals(PictureSettings(), fresh.picture)
        assertEquals(LeaveAction.STOP, fresh.leaveAction)
        assertEquals(10, fresh.seekStepSeconds)
        assertTrue(fresh.profiles.isEmpty())
    }

    @Test
    fun rememberHistoryOffKeepsNoHistory() {
        preferences.rememberHistory = false
        open("long_60s.mp4").use { it.waitForProgress(1_000) }
        assertNull(history.find(TestMediaProvider.uri("long_60s.mp4").toString()))
    }

    @Test
    fun everyScreenOpens() {
        ActivityScenario.launch(HomeActivity::class.java).use { }
        ActivityScenario.launch(SettingsActivity::class.java).use { }
        ActivityScenario.launch(LibraryActivity::class.java).use { }
        ActivityScenario.launch(PlaylistsActivity::class.java).use { }
        val id = library.createPlaylist("Test")
        val intent = Intent(context, PlaylistActivity::class.java).putExtra(PlaylistActivity.EXTRA_ID, id)
        ActivityScenario.launch<PlaylistActivity>(intent).use { }
    }

    @Test
    fun theControlsHideSoTheScreenIsAllVideoAndATapBringsThemBack() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            waitUntil("controls hidden", 8_000) { scenario.read { it.controlsView.visibility } == View.GONE }
            waitUntil("system bars hidden", 3_000) {
                val root = scenario.read { it.window.decorView }
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
                    !scenario.read { root.rootWindowInsets }.isVisible(android.view.WindowInsets.Type.navigationBars())
                } else {
                    @Suppress("DEPRECATION")
                    scenario.read { root.systemUiVisibility } and View.SYSTEM_UI_FLAG_HIDE_NAVIGATION != 0
                }
            }
            val tapped = SystemClock.uptimeMillis()
            scenario.onActivity { activity ->
                val layer = activity.findViewById<View>(R.id.gestureLayer)
                for (action in listOf(MotionEvent.ACTION_DOWN, MotionEvent.ACTION_UP)) {
                    val event = MotionEvent.obtain(tapped, SystemClock.uptimeMillis(), action, layer.width / 2f, layer.height / 2f, 0)
                    layer.dispatchTouchEvent(event)
                    event.recycle()
                }
            }
            waitUntil("controls back", 3_000) { scenario.read { it.controlsView.visibility } == View.VISIBLE }
        }
    }

    @Test
    fun theBottomTabsOpenTheirScreens() {
        val tabs = listOf(
            R.id.navLibrary to LibraryActivity::class.java,
            R.id.navPlaylists to PlaylistsActivity::class.java,
            R.id.navSettings to SettingsActivity::class.java,
        )
        ActivityScenario.launch(HomeActivity::class.java).use { home ->
            for ((tab, target) in tabs) {
                val monitor = instrumentation.addMonitor(target.name, null, false)
                try {
                    home.onActivity { it.findViewById<View>(tab).performClick() }
                    val opened = instrumentation.waitForMonitorWithTimeout(monitor, 8_000)
                    assertNotNull("${target.simpleName} did not open", opened)
                    opened!!.finish()
                } finally {
                    instrumentation.removeMonitor(monitor)
                }
            }
        }
    }

    @Test
    fun theButtonsNameThemselvesForScreenReaders() {
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            val ids = listOf(
                R.id.closeButton, R.id.moreButton, R.id.backButton, R.id.playButton, R.id.forwardButton,
                R.id.audioButton, R.id.subtitleButton, R.id.volumeButton, R.id.fitButton, R.id.rotateButton,
            )
            for (id in ids) {
                val description = scenario.read { it.findViewById<View>(id).contentDescription?.toString().orEmpty() }
                assertTrue(context.resources.getResourceEntryName(id), description.isNotBlank())
            }
            val volume = scenario.read { it.findViewById<View>(R.id.volumeButton).contentDescription.toString() }
            assertEquals(context.getString(R.string.volume_description, 100), volume)
        }
    }

    @Test
    fun aSeekStepSettingChangesTheButtons() {
        preferences.seekStepSeconds = 30
        open("long_60s.mp4").use { scenario ->
            scenario.waitForProgress()
            val label = scenario.read { it.findViewById<Button>(R.id.forwardButton).text.toString() }
            assertEquals("30", label)
            val before = scenario.read { it.currentPositionMs }
            scenario.onActivity { it.findViewById<View>(R.id.forwardButton).performClick() }
            waitUntil("moved 30 s", 5_000) { scenario.read { it.currentPositionMs } > before + 25_000 }
            assertNotEquals(before, scenario.read { it.currentPositionMs })
        }
    }
}
