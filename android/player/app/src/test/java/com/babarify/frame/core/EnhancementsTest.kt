package com.babarify.frame.core

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class EnhancementsTest {
    private val identity = floatArrayOf(
        1f, 0f, 0f, 0f, 0f,
        0f, 1f, 0f, 0f, 0f,
        0f, 0f, 1f, 0f, 0f,
        0f, 0f, 0f, 1f, 0f,
    )

    /** Applies a colour matrix the way Android does, with colours in 0..255. */
    private fun apply(m: FloatArray, r: Float, g: Float, b: Float) = Triple(
        m[0] * r + m[1] * g + m[2] * b + m[3] * 255 + m[4],
        m[5] * r + m[6] * g + m[7] * b + m[8] * 255 + m[9],
        m[10] * r + m[11] * g + m[12] * b + m[13] * 255 + m[14],
    )

    @Test
    fun defaultPictureChangesNothing() {
        assertTrue(PictureSettings().isDefault)
        assertArrayEquals(identity, PictureSettings().colorMatrix(), 0.001f)
    }

    @Test
    fun brightnessScalesColours() {
        val (r, g, b) = apply(PictureSettings(brightness = 2f).colorMatrix(), 50f, 60f, 70f)
        assertEquals(100f, r, 0.5f)
        assertEquals(120f, g, 0.5f)
        assertEquals(140f, b, 0.5f)
        val (dark, _, _) = apply(PictureSettings(brightness = 0f).colorMatrix(), 200f, 200f, 200f)
        assertEquals(0f, dark, 0.5f)
    }

    @Test
    fun contrastTurnsAroundMiddleGrey() {
        val matrix = PictureSettings(contrast = 2f).colorMatrix()
        assertEquals(127.5f, apply(matrix, 127.5f, 127.5f, 127.5f).first, 0.5f)
        assertEquals(255f, apply(matrix, 191.25f, 191.25f, 191.25f).first, 0.5f)
        val flat = PictureSettings(contrast = 0f).colorMatrix()
        assertEquals(127.5f, apply(flat, 10f, 200f, 90f).second, 0.5f)
    }

    @Test
    fun noSaturationIsGrey() {
        val (r, g, b) = apply(PictureSettings(saturation = 0f).colorMatrix(), 255f, 0f, 0f)
        assertEquals(r, g, 0.5f)
        assertEquals(g, b, 0.5f)
    }

    @Test
    fun hueTurnsColourAndLeavesGreyAlone() {
        val matrix = PictureSettings(hue = 180f).colorMatrix()
        val (r, g, b) = apply(matrix, 100f, 100f, 100f)
        assertEquals(100f, r, 1f)
        assertEquals(100f, g, 1f)
        assertEquals(100f, b, 1f)
        val (red, _, blue) = apply(matrix, 200f, 0f, 0f)
        assertTrue("red should be gone", red < blue + 60)
    }

    @Test
    fun picturesAreKeptInRange() {
        val wild = PictureSettings(9f, -1f, 99f, 720f).normalized()
        assertEquals(PictureSettings(2f, 0f, 3f, 180f), wild)
    }

    @Test
    fun equalizerIsAlwaysTenBandsInRange() {
        val settings = EqualizerSettings(true, 99f, listOf(-50f, 3f)).normalized()
        assertEquals(20f, settings.preampDb)
        assertEquals(10, settings.bandsDb.size)
        assertEquals(-20f, settings.bandsDb[0])
        assertEquals(0f, settings.bandsDb[9])
    }

    @Test
    fun aQuarterTurnShrinksToFit() {
        val turned = VideoGeometry.viewTransform(VideoTransform.ROTATE_90, 1f, 1000, 500)
        assertEquals(90f, turned.rotation)
        assertEquals(0.5f, turned.scaleX)
        val flat = VideoGeometry.viewTransform(VideoTransform.ROTATE_180, 1f, 1000, 500)
        assertEquals(1f, flat.scaleX)
    }

    @Test
    fun flipsAndZoomCombine() {
        val result = VideoGeometry.viewTransform(VideoTransform.FLIP_HORIZONTAL, 2f, 1000, 500)
        assertEquals(-2f, result.scaleX)
        assertEquals(2f, result.scaleY)
        assertEquals(-1f, VideoGeometry.viewTransform(VideoTransform.FLIP_VERTICAL, 1f, 100, 100).scaleY)
    }

    @Test
    fun fillZoomCoversTheView() {
        // 16:9 video in a tall 9:16 view is letterboxed; filling needs a zoom of about 3.16.
        assertEquals(3.16f, VideoGeometry.fillZoom(1080, 1920, 1920, 1080), 0.01f)
        assertEquals(1f, VideoGeometry.fillZoom(1920, 1080, 1920, 1080), 0.01f)
        assertEquals(1f, VideoGeometry.fillZoom(0, 0, 1920, 1080))
    }

    @Test
    fun abLoopCycle() {
        val loop = AbLoop()
        loop.press(1_000)
        assertFalse(loop.active)
        assertNull("no jump before B", loop.jumpTarget(5_000))
        loop.press(500) // Before A: moves A rather than repeating nothing.
        assertEquals(500L, loop.a)
        loop.press(3_000)
        assertTrue(loop.active)
        assertNull(loop.jumpTarget(2_000))
        assertEquals(500L, loop.jumpTarget(3_000))
        loop.press(4_000)
        assertNull(loop.a)
        assertNull(loop.b)
    }

    @Test
    fun playNextGoesAfterTheCurrentItemAndAddToQueueAtTheEnd() {
        val a = QueueItem("a", "A")
        val b = QueueItem("b", "B")
        val c = QueueItem("c", "C")
        val d = QueueItem("d", "D")
        val queue = PlayQueue(listOf(a, b, c), 1)
        val next = queue.withNext(d)
        assertEquals(listOf(a, b, d, c), next.items)
        assertEquals("still on the same song", 1, next.index)
        val last = queue.withLast(d)
        assertEquals(listOf(a, b, c, d), last.items)
        assertEquals(1, last.index)
        assertEquals(listOf(d), PlayQueue(emptyList()).withNext(d).items)
    }

    @Test
    fun removingFilesKeepsTheCurrentOne() {
        val a = QueueItem("a", "A")
        val b = QueueItem("b", "B")
        val c = QueueItem("c", "C")
        val queue = PlayQueue(listOf(a, b, c), 2).without(setOf("a"))
        assertEquals(listOf(b, c), queue.items)
        assertEquals(c, queue.items[queue.index])
    }

    @Test
    fun repeatDecidesWhatPlaysAtTheEnd() {
        val items = listOf(QueueItem("a", "A"), QueueItem("b", "B"))
        val off = PlayQueue(items, 1)
        assertNull("off stops at the end", off.afterEnd(RepeatMode.OFF))
        val first = PlayQueue(items, 0)
        assertEquals("off moves on", "B", first.afterEnd(RepeatMode.OFF)?.title)
        val one = PlayQueue(items, 1)
        assertEquals("one stays", "B", one.afterEnd(RepeatMode.ONE)?.title)
        assertEquals(1, one.index)
        val all = PlayQueue(items, 1)
        assertEquals("all goes round", "A", all.afterEnd(RepeatMode.ALL)?.title)
        assertEquals(0, all.index)
        assertEquals("a single file repeats with all", "A", PlayQueue(listOf(items[0])).afterEnd(RepeatMode.ALL)?.title)
        assertEquals("next goes round with all", "A", PlayQueue(items, 1).nextPressed(RepeatMode.ALL)?.title)
        assertNull("next stops otherwise", PlayQueue(items, 1).nextPressed(RepeatMode.ONE))
        assertNull(PlayQueue(emptyList()).afterEnd(RepeatMode.ONE))
    }

    @Test
    fun equalizerBarsStayInRangeAndMove() {
        for (bar in 0 until 16) {
            val levels = (0L until 5_000L step 40).map { EqualizerAnimation.level(bar, it) }
            assertTrue(levels.all { it in EqualizerAnimation.REST..1f })
            assertTrue("bar $bar should really move", levels.max() - levels.min() > 0.3f)
        }
        assertTrue(
            "bars shouldn't all stand alike",
            (0 until 16).map { EqualizerAnimation.level(it, 1_000) }.toSet().size > 8,
        )
    }

    @Test
    fun barsMakeAShapeAndPeaksFallSlowly() {
        val count = 19
        assertEquals(1f, EqualizerAnimation.envelope(9, count), 0.001f)
        assertTrue(EqualizerAnimation.envelope(0, count) < EqualizerAnimation.envelope(5, count))
        assertEquals(EqualizerAnimation.envelope(0, count), EqualizerAnimation.envelope(18, count), 0.001f)
        assertEquals("jumps up at once", 0.9f, EqualizerAnimation.peak(0.2f, 0.9f), 0.001f)
        val falling = EqualizerAnimation.peak(0.9f, 0.2f)
        assertTrue("falls, but slowly", falling < 0.9f && falling > 0.8f)
    }

    @Test
    fun automaticStyleVisitsEveryStyleInTurn() {
        val styles = EqualizerAnimation.CYCLE
        assertTrue(VisualStyle.AUTO !in styles)
        val seen = styles.indices.map { EqualizerAnimation.autoStyle(it * EqualizerAnimation.AUTO_SWITCH_MS + 1) }
        assertEquals(styles, seen)
        assertEquals("goes round again", styles[0], EqualizerAnimation.autoStyle(styles.size * EqualizerAnimation.AUTO_SWITCH_MS))
        assertEquals(styles[0], EqualizerAnimation.autoStyle(-5))
    }

    @Test
    fun queueMovesAndStopsAtItsEnds() {
        val queue = PlayQueue(listOf(QueueItem("a", "A"), QueueItem("b", "B")), 0)
        assertTrue(queue.isPlaylist)
        assertFalse(queue.hasPrevious)
        assertEquals("B", queue.next()?.title)
        assertNull(queue.next())
        assertEquals("A", queue.previous()?.title)
        assertNull(queue.previous())
        assertFalse(PlayQueue(listOf(QueueItem("a", "A"))).isPlaylist)
        assertEquals(1, PlayQueue(listOf(QueueItem("a", "A"), QueueItem("b", "B")), 99).index)
    }
}
