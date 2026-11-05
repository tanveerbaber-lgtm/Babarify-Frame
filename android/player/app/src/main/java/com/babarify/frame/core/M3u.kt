package com.babarify.frame.core

/** M3U playlist files. Android files have no lasting paths to share, so these match songs by file name. */
object M3u {
    /** The file named on each line, without any folder. */
    fun fileNames(text: String): List<String> = text.removePrefix(Char(0xFEFF).toString()).lineSequence()
        .map { it.trim() }
        .filter { it.isNotEmpty() && !it.startsWith("#") }
        .map { it.substringAfterLast('/').substringAfterLast('\\') }
        .toList()

    /** A playlist's text, from file names. */
    fun render(names: List<String>): String = buildString {
        append("#EXTM3U\n")
        names.forEach { append("#EXTINF:-1,").append(MusicRules.withoutExtension(it)).append('\n').append(it).append('\n') }
    }

    /** The songs named, in the playlist's order; and how many weren't on this phone. */
    fun match(names: List<String>, songs: List<Song>): Pair<List<Song>, Int> {
        val byName = songs.groupBy { it.fileName.lowercase() }
        val found = names.mapNotNull { byName[it.lowercase()]?.firstOrNull() }
        return found to names.size - found.size
    }
}
