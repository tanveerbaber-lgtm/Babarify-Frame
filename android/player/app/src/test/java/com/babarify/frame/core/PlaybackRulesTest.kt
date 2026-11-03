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
}
