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
)

enum class GroupKind { ALBUM, ARTIST, FOLDER }

/** An album, artist or folder. A blank [title] means the file doesn't say, and the screen words that. */
data class SongGroup(val kind: GroupKind, val key: String, val title: String, val songs: List<Song>)

enum class SongSort { TITLE, ARTIST, RECENTLY_ADDED, DURATION }

object MusicRules {
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

    fun sorted(songs: List<Song>, sort: SongSort): List<Song> = when (sort) {
        SongSort.TITLE -> songs.sortedBy { it.title.lowercase() }
        SongSort.ARTIST -> songs.sortedWith(compareBy({ it.artist == null }, { it.artist?.lowercase() }, { it.title.lowercase() }))
        SongSort.RECENTLY_ADDED -> songs.sortedWith(compareBy({ -it.addedAt }, { it.title.lowercase() }))
        SongSort.DURATION -> songs.sortedWith(compareBy({ -it.durationMs }, { it.title.lowercase() }))
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
