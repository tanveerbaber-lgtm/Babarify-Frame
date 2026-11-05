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
