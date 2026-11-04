package com.babarify.frame.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PlaybackRulesTest {
    @Test
    fun onlyContentAddressesAreOpened() {
        assertTrue(PlaybackRules.isOpenableScheme("content"))
        assertTrue(PlaybackRules.isOpenableScheme("CONTENT"))
        for (scheme in listOf("file", "http", "https", "rtsp", "", null)) {
            assertFalse("$scheme", PlaybackRules.isOpenableScheme(scheme))
        }
    }

    @Test
    fun resumeContinuesInTheMiddleOfAFile() {
        assertEquals(60_000, PlaybackRules.resumePosition(60_000, 600_000, finished = false))
        assertEquals(60_000, PlaybackRules.resumePosition(60_000, null, finished = false))
    }

    @Test
    fun resumeRestartsAtTheVeryStartOrEnd() {
        assertEquals(0, PlaybackRules.resumePosition(4_999, 600_000, finished = false))
        assertEquals(0, PlaybackRules.resumePosition(595_000, 600_000, finished = false))
        assertEquals(0, PlaybackRules.resumePosition(60_000, 600_000, finished = true))
    }

    // M12: libVLC reports truncated and non-media files as "ended" with no error.
    @Test
    fun anEndWithoutProgressIsAFailureNotAFinishedFile() {
        assertEquals(PlaybackState.ERROR, PlaybackRules.classifyEnd(progressed = false))
        assertEquals(PlaybackState.ENDED, PlaybackRules.classifyEnd(progressed = true))
    }

    @Test
    fun aSilentEngineTimesOutOnlyWhileTryingToPlay() {
        val limit = PlaybackRules.OPEN_TIMEOUT_MS
        assertTrue(PlaybackRules.hasOpenTimedOut(limit, progressed = false, wantsToPlay = true))
        assertFalse(PlaybackRules.hasOpenTimedOut(limit - 1, progressed = false, wantsToPlay = true))
        assertFalse(PlaybackRules.hasOpenTimedOut(limit, progressed = true, wantsToPlay = true))
        assertFalse(PlaybackRules.hasOpenTimedOut(limit, progressed = false, wantsToPlay = false))
    }

    // M13: the first file after installing waits ~22 s for libVLC's font cache on a Galaxy A33.
    @Test
    fun aSlowFirstOpenIsNotCalledAFailure() {
        assertFalse(PlaybackRules.hasOpenTimedOut(30_000, progressed = false, wantsToPlay = true))
        assertTrue(PlaybackRules.shouldShowPreparing(PlaybackState.LOADING, PlaybackRules.SHOW_PREPARING_AFTER_MS))
        assertFalse(PlaybackRules.shouldShowPreparing(PlaybackState.LOADING, 1_000))
        assertFalse(PlaybackRules.shouldShowPreparing(PlaybackState.PLAYING, 30_000))
    }

    @Test
    fun seekStaysInsideTheFile() {
        assertEquals(0, PlaybackRules.seekTarget(5_000, -10_000, 60_000))
        assertEquals(60_000, PlaybackRules.seekTarget(55_000, 10_000, 60_000))
        assertEquals(25_000, PlaybackRules.seekTarget(15_000, 10_000, null))
    }

    @Test
    fun timeIsFormattedForPeople() {
        assertEquals("0:00", PlaybackRules.formatTime(-1))
        assertEquals("1:05", PlaybackRules.formatTime(65_000))
        assertEquals("1:01:01", PlaybackRules.formatTime(3_661_000))
    }

    @Test
    fun onlySubtitleFilesAreAccepted() {
        assertEquals("srt", PlaybackRules.subtitleExtension("Film.SRT"))
        assertEquals("ass", PlaybackRules.subtitleExtension("a.b.ass"))
        assertNull(PlaybackRules.subtitleExtension("movie.mp4"))
        assertNull(PlaybackRules.subtitleExtension("noextension"))
        assertNull(PlaybackRules.subtitleExtension(null))
    }

    @Test
    fun normalVolumeIs1To100AndBoostGoesTo200() {
        assertEquals(1, PlaybackRules.clampVolume(0, allowBoost = false))
        assertEquals(100, PlaybackRules.clampVolume(150, allowBoost = false))
        assertEquals(150, PlaybackRules.clampVolume(150, allowBoost = true))
        assertEquals(200, PlaybackRules.clampVolume(999, allowBoost = true))
        assertEquals(100, PlaybackRules.rememberedVolume(200))
        assertEquals(1, PlaybackRules.rememberedVolume(0))
    }

    @Test
    fun trackLanguagesAreMatchedByWholeWords() {
        assertTrue(PlaybackRules.languageMatches("fre", "Track 2 - [French]"))
        assertTrue(PlaybackRules.languageMatches("eng", "English tone"))
        assertTrue(PlaybackRules.languageMatches("eng", "Audio [en]"))
        assertTrue(PlaybackRules.languageMatches("ger", "deu stereo"))
        assertFalse(PlaybackRules.languageMatches("eng", "Track 1"))
        assertFalse("part of a word is no match", PlaybackRules.languageMatches("eng", "Length"))
        assertFalse(PlaybackRules.languageMatches("", "English"))
    }

    @Test
    fun mediaIsToldApartFromOtherFiles() {
        assertTrue(PlaybackRules.isMediaName("Film.MKV"))
        assertTrue(PlaybackRules.isMediaName("song.flac"))
        assertFalse(PlaybackRules.isMediaName("subtitle.srt"))
        assertFalse(PlaybackRules.isMediaName("noextension"))
        assertTrue(PlaybackRules.isVideoName("a.mp4"))
        assertFalse(PlaybackRules.isVideoName("a.mp3"))
    }

    @Test
    fun audioIsToldApartFromVideo() {
        assertTrue(PlaybackRules.isAudioOnly("song.mp3", progressed = false, hasVideoTrack = false))
        assertTrue("cover art doesn't make a song a video", PlaybackRules.isAudioOnly("song.m4a", true, hasVideoTrack = true))
        assertFalse(PlaybackRules.isAudioOnly("film.mp4", progressed = true, hasVideoTrack = true))
        assertFalse("not known yet", PlaybackRules.isAudioOnly("film.mp4", progressed = false, hasVideoTrack = false))
        assertTrue("sound only, whatever the name", PlaybackRules.isAudioOnly("clip.mp4", progressed = true, hasVideoTrack = false))
    }

    @Test
    fun delaysStayInRange() {
        assertEquals(60_000, PlaybackRules.clampDelay(999_999))
        assertEquals(-60_000, PlaybackRules.clampDelay(-999_999))
        assertEquals(50, PlaybackRules.clampDelay(50))
    }

    @Test
    fun previousRestartsUnlessTheFileHasJustBegun() {
        assertTrue(PlaybackRules.previousRestartsFile(10_000, hasPrevious = true))
        assertFalse(PlaybackRules.previousRestartsFile(1_000, hasPrevious = true))
        assertTrue(PlaybackRules.previousRestartsFile(1_000, hasPrevious = false))
    }

    @Test
    fun chapterNavigation() {
        val starts = listOf(0L, 10_000L, 20_000L)
        assertEquals(1, PlaybackRules.chapterIndexAt(starts, 15_000))
        assertEquals(1, PlaybackRules.previousChapterIndex(starts, 15_000))
        assertEquals(0, PlaybackRules.previousChapterIndex(starts, 11_000))
        assertEquals(0, PlaybackRules.previousChapterIndex(starts, 500))
    }
}
