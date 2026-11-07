package com.babarify.frame.core

/** What has been listened to, worked out on this phone from the play counts. */
data class Recap(
    val plays: Int,
    val listenedMs: Long,
    val songsPlayed: Int,
    val topSongs: List<Pair<Song, Int>>,
    val topArtists: List<Pair<String, Int>>,
    val topAlbums: List<Pair<String, Int>>,
    val neverPlayed: List<Song>,
) {
    companion object {
        private const val TOP = 5

        /** [plays] gives how many times each song has been played, by its uri. */
        fun of(songs: List<Song>, plays: Map<String, Int>): Recap {
            val played = songs.mapNotNull { song -> plays[song.uri]?.takeIf { it > 0 }?.let { song to it } }
                .sortedWith(compareBy({ -it.second }, { it.first.title.lowercase() }))
            return Recap(
                plays = played.sumOf { it.second },
                listenedMs = played.sumOf { (song, times) -> song.durationMs * times },
                songsPlayed = played.size,
                topSongs = played.take(TOP),
                topArtists = top(played) { it.artist },
                topAlbums = top(played) { it.album },
                neverPlayed = songs.filter { (plays[it.uri] ?: 0) == 0 }.take(TOP),
            )
        }

        private fun top(played: List<Pair<Song, Int>>, name: (Song) -> String?): List<Pair<String, Int>> =
            played.mapNotNull { (song, times) -> name(song)?.let { it to times } }
                .groupBy({ it.first }, { it.second })
                .map { (key, counts) -> key to counts.sum() }
                .sortedWith(compareBy({ -it.second }, { it.first.lowercase() }))
                .take(TOP)
    }
}
