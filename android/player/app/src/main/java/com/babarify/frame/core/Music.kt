package com.babarify.frame.core

/** One song the phone's media index knows about. */
data class Song(
    val uri: String,
    val title: String,
    val artist: String?,
    val album: String?,
    val albumId: Long,
    val folder: String,
    val fileName: String,
    val durationMs: Long,
    val addedAt: Long,
    val year: Int? = null,
)

enum class GroupKind { ALBUM, ARTIST, FOLDER }

/** An album, artist or folder. A blank [title] means the file doesn't say, and the screen words that. */
data class SongGroup(val kind: GroupKind, val key: String, val title: String, val songs: List<Song>)

enum class SongSort { TITLE, ARTIST, FOLDER, RECENTLY_ADDED, OLDEST_ADDED, MOST_PLAYED, YEAR, DURATION }

object MusicRules {
    val FADE_CHOICES_S = listOf(0, 2, 4, 6)

    /** Sound effects, as libVLC audio filters. */
    val AUDIO_EFFECTS = linkedMapOf(
        "none" to "",
        "room" to "spatializer",
        "wide" to "stereo_widen",
        "both" to "spatializer:stereo_widen",
    )

    /** The volume [ms] into a fade in, or [ms] before the end of a fade out. */
    fun fadeLevel(base: Int, ms: Long, fadeMs: Long): Int =
        if (fadeMs <= 0) base else Math.round(base * ms.coerceIn(0, fadeMs).toDouble() / fadeMs).toInt()

    private const val UNKNOWN = "<unknown>"
    private val BASS_WEIGHTS = listOf(1f, 0.8f, 0.5f, 0.2f)

    /** The most a full bass dial adds to the lowest band, in dB. */
    const val BASS_MAX_DB = 12f

    /** Android's index writes "<unknown>" for a missing tag. */
    fun tagOrNull(raw: String?): String? = raw?.trim()?.takeIf { it.isNotEmpty() && it != UNKNOWN }

    /** "Music/Road trip/" is the folder "Road trip". */
    fun folderName(relativePath: String?): String =
        relativePath.orEmpty().trimEnd('/').substringAfterLast('/')

    fun withoutExtension(name: String): String {
        val dot = name.lastIndexOf('.')
        return if (dot > 0 && name.length - dot <= MAX_EXTENSION) name.substring(0, dot) else name
    }

    fun groups(songs: List<Song>, kind: GroupKind): List<SongGroup> {
        val grouped = songs.groupBy { song ->
            when (kind) {
                GroupKind.ALBUM -> song.albumId.toString()
                GroupKind.ARTIST -> song.artist.orEmpty().lowercase()
                GroupKind.FOLDER -> song.folder
            }
        }
        return grouped.map { (key, members) ->
            val first = members.first()
            val title = when (kind) {
                GroupKind.ALBUM -> first.album
                GroupKind.ARTIST -> first.artist
                GroupKind.FOLDER -> first.folder
            }.orEmpty()
            SongGroup(kind, key, title, sorted(members, SongSort.TITLE))
        }.sortedWith(compareBy({ it.title.isEmpty() }, { it.title.lowercase() }))
    }

    /** [plays] says how many times each song has been played, by its uri, for sorting by that. */
    fun sorted(songs: List<Song>, sort: SongSort, plays: Map<String, Int> = emptyMap()): List<Song> = when (sort) {
        SongSort.TITLE -> songs.sortedBy { it.title.lowercase() }
        SongSort.ARTIST -> songs.sortedWith(compareBy({ it.artist == null }, { it.artist?.lowercase() }, { it.title.lowercase() }))
        SongSort.RECENTLY_ADDED -> songs.sortedWith(compareBy({ -it.addedAt }, { it.title.lowercase() }))
        SongSort.DURATION -> songs.sortedWith(compareBy({ -it.durationMs }, { it.title.lowercase() }))
        SongSort.OLDEST_ADDED -> songs.sortedWith(compareBy({ it.addedAt }, { it.title.lowercase() }))
        SongSort.FOLDER -> songs.sortedWith(compareBy({ it.folder.lowercase() }, { it.title.lowercase() }))
        SongSort.YEAR -> songs.sortedWith(compareBy({ it.year == null }, { -(it.year ?: 0) }, { it.title.lowercase() }))
        SongSort.MOST_PLAYED -> songs.sortedWith(compareBy({ -(plays[it.uri] ?: 0) }, { it.title.lowercase() }))
    }

    fun search(songs: List<Song>, text: String): List<Song> {
        val needle = text.trim()
        if (needle.isEmpty()) return songs
        return songs.filter { song ->
            listOfNotNull(song.title, song.artist, song.album).any { it.contains(needle, ignoreCase = true) }
        }
    }

    /**
     * The bass dial turns up the lowest bands. Changing it moves them by the difference, so changes the
     * user made to those bands by hand are kept. [oldBass] and [newBass] run from 0 to 1.
     */
    fun withBass(bandsDb: List<Float>, oldBass: Float, newBass: Float, minDb: Float, maxDb: Float): List<Float> =
        bandsDb.mapIndexed { band, value ->
            val weight = BASS_WEIGHTS.getOrElse(band) { 0f }
            (value + (newBass - oldBass) * BASS_MAX_DB * weight).coerceIn(minDb, maxDb)
        }

    private const val MAX_EXTENSION = 6
}
