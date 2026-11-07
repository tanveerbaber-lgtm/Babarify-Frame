package com.babarify.frame.core

import kotlin.random.Random
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MusicRulesTest {
    private fun song(
        title: String,
        artist: String? = null,
        album: String? = null,
        albumId: Long = 0,
        folder: String = "",
        durationMs: Long = 1,
        addedAt: Long = 0,
    ) = Song("content://media/$title", title, artist, album, albumId, folder, "$title.mp3", durationMs, addedAt)

    @Test
    fun fadesRiseAndFallWithTheTime() {
        assertEquals(0, MusicRules.fadeLevel(80, 0, 4000))
        assertEquals(40, MusicRules.fadeLevel(80, 2000, 4000))
        assertEquals(80, MusicRules.fadeLevel(80, 9000, 4000))
        assertEquals(0, MusicRules.fadeLevel(80, -5, 4000))
        assertEquals("off", 80, MusicRules.fadeLevel(80, 100, 0))
    }

    @Test
    fun theRecapCountsWhatWasPlayed() {
        val one = song("One", artist = "Zed", durationMs = 60_000).copy(uri = "u1", album = "Hits")
        val two = song("Two", artist = "Zed", durationMs = 120_000).copy(uri = "u2", album = "Hits")
        val three = song("Three", durationMs = 30_000).copy(uri = "u3", album = null)
        val recap = Recap.of(listOf(one, two, three), mapOf("u1" to 3, "u2" to 1, "other" to 9))
        assertEquals(4, recap.plays)
        assertEquals(2, recap.songsPlayed)
        assertEquals(300_000L, recap.listenedMs)
        assertEquals(listOf("One", "Two"), recap.topSongs.map { it.first.title })
        assertEquals(listOf("Zed" to 4), recap.topArtists)
        assertEquals(listOf("Hits" to 4), recap.topAlbums)
        assertEquals(listOf("Three"), recap.neverPlayed.map { it.title })
    }

    @Test
    fun lyricsAreReadAndFollowed() {
        val text = "[ar:Someone]\n[00:12.50]Second\n[00:05.00][00:30.00]First\n\n"
        val lines = Lyrics.parse(text)
        assertEquals(listOf("First", "Second", "First"), lines.map { it.text })
        assertEquals(listOf(5_000L, 12_500L, 30_000L), lines.map { it.timeMs })
        assertEquals(-1, Lyrics.currentLine(lines, 4_999))
        assertEquals(0, Lyrics.currentLine(lines, 5_000))
        assertEquals(1, Lyrics.currentLine(lines, 29_999))
        assertEquals(2, Lyrics.currentLine(lines, 99_000))
        val plain = Lyrics.parse("\nOne\n\nTwo\n")
        assertEquals(listOf("One", "", "Two"), plain.map { it.text })
        assertEquals("no timing, nothing to follow", -1, Lyrics.currentLine(plain, 50_000))
    }

    @Test
    fun anM3uFileIsReadAndMatchedByFileName() {
        val text = "\uFEFF#EXTM3U\r\n#EXTINF:12,One\r\nC:\\Music\\one.mp3\r\n\r\n../two.MP3\nhttp://x/three.mp3\n"
        val names = M3u.fileNames(text)
        assertEquals(listOf("one.mp3", "two.MP3", "three.mp3"), names)
        val one = song("one").copy(fileName = "one.mp3", uri = "u1")
        val two = song("two").copy(fileName = "two.mp3", uri = "u2")
        val (found, missing) = M3u.match(names, listOf(two, one))
        assertEquals(listOf(one, two), found)
        assertEquals(1, missing)
        assertEquals(names, M3u.fileNames(M3u.render(names)))
    }

    @Test
    fun missingTagsAreToldApart() {
        assertNull(MusicRules.tagOrNull("<unknown>"))
        assertNull(MusicRules.tagOrNull("  "))
        assertNull(MusicRules.tagOrNull(null))
        assertEquals("Queen", MusicRules.tagOrNull(" Queen "))
    }

    @Test
    fun foldersAndNamesReadWell() {
        assertEquals("Road trip", MusicRules.folderName("Music/Road trip/"))
        assertEquals("", MusicRules.folderName(null))
        assertEquals("Song", MusicRules.withoutExtension("Song.mp3"))
        assertEquals("Mr. Blue Sky live version", MusicRules.withoutExtension("Mr. Blue Sky live version"))
        assertEquals(".hidden", MusicRules.withoutExtension(".hidden"))
    }

    @Test
    fun songsGroupWithUnknownsLast() {
        val songs = listOf(
            song("b", artist = "Zed", album = "Two", albumId = 2, folder = "Rock"),
            song("a", artist = "zed", album = "Two", albumId = 2, folder = "Rock"),
            song("c", album = "One", albumId = 1, folder = "Pop"),
        )
        val artists = MusicRules.groups(songs, GroupKind.ARTIST)
        assertEquals(listOf("Zed", ""), artists.map { it.title })
        assertEquals("different capitals are one artist", listOf("a", "b"), artists[0].songs.map { it.title })
        assertEquals(listOf("One", "Two"), MusicRules.groups(songs, GroupKind.ALBUM).map { it.title })
        assertEquals(listOf("Pop", "Rock"), MusicRules.groups(songs, GroupKind.FOLDER).map { it.title })
    }

    @Test
    fun songsSortAndSearch() {
        val songs = listOf(
            song("Beta", artist = "Abba", durationMs = 5, addedAt = 1),
            song("alpha", artist = "Zed", durationMs = 9, addedAt = 3),
            song("Gamma", durationMs = 1, addedAt = 2),
        )
        assertEquals(listOf("alpha", "Beta", "Gamma"), MusicRules.sorted(songs, SongSort.TITLE).map { it.title })
        assertEquals(listOf("Beta", "alpha", "Gamma"), MusicRules.sorted(songs, SongSort.ARTIST).map { it.title })
        assertEquals(listOf("alpha", "Gamma", "Beta"), MusicRules.sorted(songs, SongSort.RECENTLY_ADDED).map { it.title })
        assertEquals(listOf("alpha", "Beta", "Gamma"), MusicRules.sorted(songs, SongSort.DURATION).map { it.title })
        assertEquals(listOf("Beta"), MusicRules.search(songs, " abba ").map { it.title })
        assertEquals(listOf("Beta", "Gamma", "alpha"), MusicRules.sorted(songs, SongSort.OLDEST_ADDED).map { it.title })
        val more = listOf(
            song("a").copy(year = 1999, folder = "Zed", uri = "u1"),
            song("b").copy(year = 2024, folder = "Abc", uri = "u2"),
            song("c").copy(year = null, folder = "Mid", uri = "u3"),
        )
        assertEquals(listOf("b", "a", "c"), MusicRules.sorted(more, SongSort.YEAR).map { it.title })
        assertEquals(listOf("b", "c", "a"), MusicRules.sorted(more, SongSort.FOLDER).map { it.title })
        assertEquals(
            listOf("c", "a", "b"),
            MusicRules.sorted(more, SongSort.MOST_PLAYED, mapOf("u3" to 5, "u1" to 2)).map { it.title },
        )
        assertEquals(3, MusicRules.search(songs, "").size)
    }

    @Test
    fun theBassDialMovesOnlyLowBandsAndKeepsHandChanges() {
        val flat = List(10) { 0f }
        val full = MusicRules.withBass(flat, 0f, 1f, -20f, 20f)
        assertEquals(MusicRules.BASS_MAX_DB, full[0], 0.001f)
        assertTrue(full[1] < full[0] && full[2] < full[1] && full[3] < full[2])
        assertEquals(0f, full[4], 0.001f)
        val byHand = full.toMutableList().also { it[0] = 15f }
        val back = MusicRules.withBass(byHand, 1f, 0f, -20f, 20f)
        assertEquals(3f, back[0], 0.001f)
        assertEquals("stays in range", 20f, MusicRules.withBass(List(10) { 19f }, 0f, 1f, -20f, 20f)[0], 0.001f)
    }

    @Test
    fun shufflingKeepsTheCurrentItemAndEveryItem() {
        val items = List(20) { QueueItem("content://$it", "$it") }
        val queue = PlayQueue(items, 7)
        val mixed = queue.shuffled(Random(1))
        assertEquals(items[7], mixed.items[mixed.index])
        assertEquals(items.toSet(), mixed.items.toSet())
        assertTrue("the order changes", mixed.items != items)
        val back = queue.at(items[3])
        assertEquals(3, back.index)
    }

    @Test
    fun aQueueJumpsOnlyToItemsItHas() {
        val queue = PlayQueue(List(3) { QueueItem("content://$it", "$it") })
        assertEquals("2", queue.jumpTo(2)?.title)
        assertEquals(2, queue.index)
        assertNull(queue.jumpTo(9))
        assertEquals(2, queue.index)
    }
}
