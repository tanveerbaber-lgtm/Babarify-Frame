package com.babarify.frame.core

/** Lyrics the person supplies. Nothing is looked up online. */
object Lyrics {
    data class Line(val timeMs: Long?, val text: String)

    private val TAG = Regex("""\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?]""")
    private val METADATA = Regex("""^\[[a-zA-Z]+:.*]$""")

    /** Lines in time order when any line has a time, otherwise as written. */
    fun parse(text: String): List<Line> {
        val timed = mutableListOf<Line>()
        val plain = mutableListOf<Line>()
        for (raw in text.removePrefix(Char(0xFEFF).toString()).lineSequence()) {
            val line = raw.trim()
            if (METADATA.matches(line)) continue
            val tags = TAG.findAll(line).toList()
            val words = TAG.replace(line, "").trim()
            if (tags.isEmpty()) {
                plain += Line(null, words)
            } else {
                tags.forEach { timed += Line(milliseconds(it), words) }
            }
        }
        if (timed.isNotEmpty()) return timed.sortedBy { it.timeMs }
        return plain.dropWhile { it.text.isEmpty() }.dropLastWhile { it.text.isEmpty() }
    }

    /** The line being sung; -1 before the first line, or when the lyrics have no timing. */
    fun currentLine(lines: List<Line>, positionMs: Long): Int {
        var found = -1
        for ((index, line) in lines.withIndex()) {
            val time = line.timeMs ?: break
            if (time > positionMs) break
            found = index
        }
        return found
    }

    private fun milliseconds(tag: MatchResult): Long {
        val (minutes, seconds, fraction) = tag.destructured
        return (minutes.toLong() * 60 + seconds.toLong()) * 1000 + fraction.padEnd(3, '0').toLong()
    }
}
