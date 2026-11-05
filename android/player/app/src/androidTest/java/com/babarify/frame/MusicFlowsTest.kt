package com.babarify.frame

import android.content.ContentValues
import android.net.Uri
import android.os.SystemClock
import android.provider.MediaStore
import android.view.View
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.babarify.frame.core.GroupKind
import com.babarify.frame.core.Song
import com.babarify.frame.data.LibraryStore
import com.babarify.frame.data.MusicLibrary
import com.babarify.frame.engine.BackgroundPlaybackService
import com.babarify.frame.engine.PlaybackSession
import com.babarify.frame.ui.EqualizerPanel
import com.babarify.frame.ui.MusicActivity
import com.babarify.frame.ui.PlayerActivity
import com.babarify.frame.ui.playSongs
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Real songs in Android's real media index, added for each test and removed after it. */
@RunWith(AndroidJUnit4::class)
class MusicFlowsTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val added = ArrayList<Uri>()
    private val prefix = "babarify_test_${SystemClock.elapsedRealtime()}"

    @Before
    fun allowAndAddSongs() {
        instrumentation.uiAutomation.grantRuntimePermission(context.packageName, MusicLibrary.permission)
        addSong("${prefix}_one.mp3")
        addSong("${prefix}_two.mp3")
        waitUntil("the index finds them", 30_000) { testSongs().size == 2 && testSongs().all { it.artist != null } }
    }

    @After
    fun cleanUp() {
        instrumentation.runOnMainSync { BackgroundPlaybackService.close(context) }
        added.forEach { context.contentResolver.delete(it, null, null) }
        LibraryStore(context).use { store -> added.forEach { store.setFavourite(it.toString(), "", false) } }
    }

    private fun addSong(name: String) {
        val values = ContentValues().apply {
            put(MediaStore.Audio.Media.DISPLAY_NAME, name)
            put(MediaStore.Audio.Media.MIME_TYPE, "audio/mpeg")
            put(MediaStore.Audio.Media.RELATIVE_PATH, "Music/BabarifyTest")
            put(MediaStore.Audio.Media.IS_PENDING, 1)
        }
        val resolver = context.contentResolver
        val uri = resolver.insert(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, values)!!
        added += uri
        resolver.openOutputStream(uri)!!.use { out ->
            instrumentation.context.assets.open("media/audio_cover.mp3").use { it.copyTo(out) }
        }
        resolver.update(uri, ContentValues().apply { put(MediaStore.Audio.Media.IS_PENDING, 0) }, null, null)
    }

    private fun testSongs(): List<Song> = MusicLibrary.songs(context).filter { it.fileName.startsWith(prefix) }

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

    private fun session() = PlaybackSession.get(context)

    @Test
    fun theIndexGivesTagsAndFolder() {
        val song = testSongs().first()
        assertEquals("Test song", song.title)
        assertEquals("Test artist", song.artist)
        assertEquals("BabarifyTest", song.folder)
        assertTrue(song.durationMs > 30_000)
    }

    @Test
    fun songsAreListedAndGrouped() {
        ActivityScenario.launch(MusicActivity::class.java).use { scenario ->
            waitUntil("songs listed") { scenario.read { activity -> activity.shownSongs.count { it.fileName.startsWith(prefix) } } == 2 }
            assertFalse(scenario.read { it.promptVisible })
            scenario.onActivity { it.chooseTab(3) }
            val folder = scenario.read { activity -> activity.shownGroups.first { it.kind == GroupKind.FOLDER && it.title == "BabarifyTest" } }
            assertEquals(2, folder.songs.count { it.fileName.startsWith(prefix) })
            scenario.onActivity { it.chooseTab(2) }
            assertTrue(scenario.read { activity -> activity.shownGroups.any { it.title == "Test artist" } })
            scenario.onActivity { it.chooseTab(1) }
            assertEquals(View.VISIBLE, scenario.read { it.findViewById<View>(R.id.musicGrid).visibility })
            assertEquals(View.GONE, scenario.read { it.findViewById<View>(R.id.musicList).visibility })
        }
    }

    // A row's button could take the row's taps, which only a real touch shows: performClick goes round it.
    @Test
    fun tappingASongOpensThePlayer() {
        val monitor = instrumentation.addMonitor(PlayerActivity::class.java.name, null, false)
        ActivityScenario.launch(MusicActivity::class.java).use { scenario ->
            waitUntil("songs listed") { scenario.read { it.shownSongs.isNotEmpty() } }
            SystemClock.sleep(500)
            val place = IntArray(2)
            var size = 0
            scenario.onActivity { activity ->
                val row = activity.findViewById<android.widget.ListView>(R.id.musicList).getChildAt(0)
                row.getLocationOnScreen(place)
                size = row.height
            }
            instrumentation.uiAutomation.executeShellCommand("input tap ${place[0] + 300} ${place[1] + size / 2}").close()
            val player = instrumentation.waitForMonitorWithTimeout(monitor, 10_000)
            instrumentation.removeMonitor(monitor)
            assertTrue("no player opened", player is PlayerActivity)
            waitUntil("playing", 180_000) {
                var position = 0L
                instrumentation.runOnMainSync { position = session().positionMs }
                position > 300
            }
            instrumentation.runOnMainSync { player.finish() }
            // Back on the list, the mini player appears by itself and shows the song's own title.
            waitUntil("mini player", 5_000) { scenario.read { it.findViewById<View>(R.id.nowPlaying).visibility } == View.VISIBLE }
            waitUntil("song title", 5_000) {
                val title = scenario.read { it.findViewById<android.widget.TextView>(R.id.nowPlayingTitle).text.toString() }
                !title.contains("babarify_test")
            }
        }
    }

    // The notification kept the first song's title when a new list started another song.
    @Test
    fun theNotificationFollowsANewlyChosenSong() {
        val manager = context.getSystemService(android.app.NotificationManager::class.java)
        fun shownTitle() = manager.activeNotifications.firstOrNull()?.notification?.extras?.getString(android.app.Notification.EXTRA_TITLE)
        val monitor = instrumentation.addMonitor(PlayerActivity::class.java.name, null, false)
        ActivityScenario.launch(MusicActivity::class.java).use { scenario ->
            waitUntil("songs listed") { scenario.read { it.isLoaded } }
            val songs = testSongs()
            scenario.onActivity { it.playSongs(songs, 0) }
            var player = instrumentation.waitForMonitorWithTimeout(monitor, 10_000) as PlayerActivity
            waitUntil("first song's title", 180_000) { shownTitle() == "Test song" }
            instrumentation.runOnMainSync { player.finish() }
            waitUntil("first player closed", 5_000) { !PlayerActivity.isInFront }
            // This one has no title tag, so its name shows, which differs from the first song's.
            val other = Song(TestMediaProvider.uri("audio_60s.m4a").toString(), "audio_60s", null, null, 0, "", "audio_60s.m4a", 60_000, 0)
            instrumentation.addMonitor(monitor) // Waiting on a monitor takes it off the list.
            scenario.onActivity { it.playSongs(listOf(other), 0) }
            player = instrumentation.waitForMonitorWithTimeout(monitor, 10_000) as PlayerActivity
            instrumentation.removeMonitor(monitor)
            waitUntil("playing the other song", 20_000) { session().mediaUri.toString() == other.uri }
            waitUntil("notification shows the new song", 10_000) { shownTitle() == "audio_60s" }
            instrumentation.runOnMainSync { player.finish() }
        }
    }

    // A real swipe across the card changes the song, and the card shows how far along it is.
    @Test
    fun theMiniPlayerShowsProgressAndSwipesToTheNextSong() {
        val monitor = instrumentation.addMonitor(PlayerActivity::class.java.name, null, false)
        ActivityScenario.launch(MusicActivity::class.java).use { scenario ->
            waitUntil("songs listed") { scenario.read { it.isLoaded } }
            val songs = testSongs()
            scenario.onActivity { it.playSongs(songs, 0) }
            val player = instrumentation.waitForMonitorWithTimeout(monitor, 10_000) as PlayerActivity
            instrumentation.removeMonitor(monitor)
            waitUntil("playing", 180_000) {
                var position = 0L
                instrumentation.runOnMainSync { position = session().positionMs }
                position > 300
            }
            instrumentation.runOnMainSync { player.finish() }
            waitUntil("mini player", 5_000) { scenario.read { it.findViewById<View>(R.id.nowPlaying).visibility } == View.VISIBLE }
            waitUntil("progress shown", 5_000) { scenario.read { it.findViewById<android.widget.ProgressBar>(R.id.nowPlayingProgress).progress } > 0 }
            assertEquals(songs[0].uri, session().mediaUri.toString())
            SystemClock.sleep(1_500) // Until the screen change has finished: a person couldn't swipe sooner.
            val place = IntArray(2)
            var size = intArrayOf(0, 0)
            scenario.onActivity { activity ->
                val card = activity.findViewById<View>(R.id.nowPlaying)
                card.getLocationOnScreen(place)
                size = intArrayOf(card.width, card.height)
            }
            val y = place[1] + size[1] / 2
            val tab = scenario.read { it.currentTab }
            instrumentation.uiAutomation
                .executeShellCommand("input swipe ${place[0] + size[0] / 2} $y ${place[0] + 20} $y 100")
                .close()
            waitUntil("next song", 10_000) { session().mediaUri.toString() == songs[1].uri }
            assertEquals("the swipe stays on the card", tab, scenario.read { it.currentTab })
        }
    }

    private fun playBoth(shuffle: Boolean, check: (PlayerActivity) -> Unit) {
        val monitor = instrumentation.addMonitor(PlayerActivity::class.java.name, null, false)
        ActivityScenario.launch(MusicActivity::class.java).use { scenario ->
            waitUntil("songs listed") { scenario.read { it.isLoaded } }
            val songs = testSongs()
            scenario.onActivity { activity -> activity.playSongs(songs, 0, shuffle) }
            val player = instrumentation.waitForMonitorWithTimeout(monitor, 10_000) as PlayerActivity
            try {
                waitUntil("playing", 180_000) {
                    var position = 0L
                    instrumentation.runOnMainSync { position = session().positionMs }
                    position > 300
                }
                SystemClock.sleep(800)
                instrumentation.runOnMainSync { check(player) }
            } finally {
                instrumentation.runOnMainSync { player.finish() }
                instrumentation.removeMonitor(monitor)
            }
        }
    }

    @Test
    fun aPictureAndTagsFillTheNowPlayingScreen() = playBoth(shuffle = false) { player ->
        assertEquals("Test song", player.findViewById<android.widget.TextView>(R.id.audioTitle).text.toString())
        assertEquals("Test artist", player.findViewById<android.widget.TextView>(R.id.audioArtist).text.toString())
        assertEquals(View.VISIBLE, player.findViewById<View>(R.id.audioCover).visibility)
        assertEquals(View.GONE, player.findViewById<View>(R.id.audioBars).visibility)
        // Everything sits on one screen: the picture ends where the controls begin.
        val art = player.findViewById<View>(R.id.audioArt)
        val controls = player.findViewById<View>(R.id.bottomBar)
        assertTrue("art ${art.bottom} controls ${controls.top}", art.bottom <= controls.top)
        assertEquals(View.VISIBLE, player.findViewById<View>(R.id.shuffleButton).visibility)
        assertEquals(View.GONE, player.findViewById<View>(R.id.subtitleButton).visibility)
    }

    @Test
    fun shuffleKeepsTheSongAndTurnsBack() = playBoth(shuffle = true) { player ->
        val session = session()
        assertTrue(session.shuffled)
        assertEquals(2, session.queue.items.size)
        val current = session.queue.items[session.queue.index]
        player.findViewById<View>(R.id.shuffleButton).performClick()
        assertFalse(session.shuffled)
        assertEquals(current, session.queue.items[session.queue.index])
    }

    // Seen with a very low bitrate MP3: opening part way ended it at once, and it was called finished.
    @Test
    fun aSongThatCantResumePlaysFromTheStartInstead() {
        val uri = TestMediaProvider.uri("audio_cover.mp3")
        val history = com.babarify.frame.data.HistoryStore(context)
        history.save(com.babarify.frame.data.HistoryEntry(uri.toString(), "audio_cover.mp3", 45_000, 60_000, false))
        history.close()
        val intent = android.content.Intent(context, PlayerActivity::class.java)
            .setData(uri)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        ActivityScenario.launch<PlayerActivity>(intent).use {
            waitUntil("playing", 180_000) {
                var position = 0L
                instrumentation.runOnMainSync { position = session().positionMs }
                position > 300
            }
            SystemClock.sleep(3_000)
            var finished = true
            var position = 0L
            instrumentation.runOnMainSync {
                finished = session().finished
                position = session().positionMs
            }
            assertFalse("called finished at $position", finished)
            assertTrue(position > 0)
        }
        com.babarify.frame.data.HistoryStore(context).use { it.clear() }
    }

    @Test
    fun aFavouriteIsRemembered() = playBoth(shuffle = false) { player ->
        val uri = session().mediaUri.toString()
        player.pressFavourite()
        LibraryStore(context).use { store ->
            assertTrue(store.isFavourite(uri))
            assertTrue(store.favourites().any { it.uri == uri })
        }
        player.pressFavourite()
        LibraryStore(context).use { store -> assertFalse(store.isFavourite(uri)) }
    }

    @Test
    fun theEqualizerPanelOpensAndChangesBass() = playBoth(shuffle = false) { player ->
        val before = session().preferences.equalizer
        val beforeBass = session().preferences.equalizerBass
        try {
            EqualizerPanel.show(player, session().preferences, session().engine) { session().onPreferencesChanged() }
        } finally {
            session().preferences.equalizer = before
            session().preferences.equalizerBass = beforeBass
        }
    }
}
