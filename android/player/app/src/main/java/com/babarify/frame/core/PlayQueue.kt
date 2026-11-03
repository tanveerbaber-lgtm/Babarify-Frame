package com.babarify.frame.core

/** The files that play one after another: a playlist, or just the one file that was opened. */
class PlayQueue(val items: List<QueueItem>, startIndex: Int = 0) {
    var index = startIndex.coerceIn(0, (items.size - 1).coerceAtLeast(0))
        private set

    val hasNext: Boolean get() = index + 1 < items.size
    val hasPrevious: Boolean get() = index > 0
    val isPlaylist: Boolean get() = items.size > 1

    fun next(): QueueItem? = if (hasNext) items[++index] else null

    fun previous(): QueueItem? = if (hasPrevious) items[--index] else null
}

/** A-B repeat: the first press sets A, the second sets B and starts repeating, the third clears. */
class AbLoop {
    var a: Long? = null
        private set
    var b: Long? = null
        private set

    val active: Boolean get() = a != null && b != null

    fun press(positionMs: Long) {
        val start = a
        when {
            start == null -> a = positionMs
            b == null && positionMs > start -> b = positionMs
            b == null -> a = positionMs // Pressed again at or before A: move A rather than repeat nothing.
            else -> clear()
        }
    }

    fun clear() {
        a = null
        b = null
    }

    /** Where to jump, once playback has passed B. */
    fun jumpTarget(positionMs: Long): Long? {
        val start = a ?: return null
        val end = b ?: return null
        return if (positionMs >= end) start else null
    }
}
