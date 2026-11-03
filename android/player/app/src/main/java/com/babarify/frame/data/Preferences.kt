package com.babarify.frame.data

import android.content.Context
import com.babarify.frame.core.EnhancementProfile
import com.babarify.frame.core.EqualizerSettings
import com.babarify.frame.core.LeaveAction
import com.babarify.frame.core.PictureSettings
import com.babarify.frame.core.PlaybackRules
import com.babarify.frame.core.SortOrder
import com.babarify.frame.core.SubtitleStyle
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/** Stored on this phone only; anything unreadable falls back to its default, as on desktop. */
class Preferences(context: Context) {
    private val store = context.applicationContext.getSharedPreferences("preferences", Context.MODE_PRIVATE)

    var hardwareDecoding: Boolean
        get() = store.getBoolean("hardware_decoding", true)
        set(value) = store.edit().putBoolean("hardware_decoding", value).apply()

    var resumePlayback: Boolean
        get() = store.getBoolean("resume_playback", true)
        set(value) = store.edit().putBoolean("resume_playback", value).apply()

    var rememberHistory: Boolean
        get() = store.getBoolean("remember_history", true)
        set(value) = store.edit().putBoolean("remember_history", value).apply()

    var seekPreviews: Boolean
        get() = store.getBoolean("seek_previews", true)
        set(value) = store.edit().putBoolean("seek_previews", value).apply()

    var gestures: Boolean
        get() = store.getBoolean("gestures", true)
        set(value) = store.edit().putBoolean("gestures", value).apply()

    var subtitlesAuto: Boolean
        get() = store.getBoolean("subtitles_auto", false)
        set(value) = store.edit().putBoolean("subtitles_auto", value).apply()

    var allowVolumeBoost: Boolean
        get() = store.getBoolean("allow_volume_boost", false)
        set(value) = store.edit().putBoolean("allow_volume_boost", value).apply()

    var rememberVolume: Boolean
        get() = store.getBoolean("remember_volume", true)
        set(value) = store.edit().putBoolean("remember_volume", value).apply()

    var volume: Int
        get() = PlaybackRules.rememberedVolume(store.getInt("volume", PlaybackRules.VOLUME_NORMAL_MAX))
        set(value) = store.edit().putInt("volume", PlaybackRules.rememberedVolume(value)).apply()

    var seekStepSeconds: Int
        get() = store.getInt("seek_step_s", 10).takeIf { it in PlaybackRules.SEEK_STEPS_S } ?: 10
        set(value) = store.edit().putInt("seek_step_s", value).apply()

    var preferredAudioLanguage: String
        get() = language("preferred_audio_language")
        set(value) = store.edit().putString("preferred_audio_language", value).apply()

    var preferredSubtitleLanguage: String
        get() = language("preferred_subtitle_language")
        set(value) = store.edit().putString("preferred_subtitle_language", value).apply()

    private fun language(key: String): String =
        store.getString(key, "")?.takeIf { it in PlaybackRules.LANGUAGES } ?: ""

    var leaveAction: LeaveAction
        get() = enumValue("leave_action", LeaveAction.STOP)
        set(value) = store.edit().putString("leave_action", value.name).apply()

    var librarySort: SortOrder
        get() = enumValue("library_sort", SortOrder.NAME)
        set(value) = store.edit().putString("library_sort", value.name).apply()

    private inline fun <reified T : Enum<T>> enumValue(key: String, default: T): T =
        enumValues<T>().firstOrNull { it.name == store.getString(key, null) } ?: default

    var subtitleStyle: SubtitleStyle
        get() = json("subtitle_style")?.let { o ->
            SubtitleStyle(
                o.optInt("size_pct", 100),
                o.optInt("text_color", 0xFFFFFF),
                o.optInt("background_opacity", 0),
            ).normalized()
        } ?: SubtitleStyle()
        set(value) {
            val o = JSONObject()
                .put("size_pct", value.sizePct)
                .put("text_color", value.textColor)
                .put("background_opacity", value.backgroundOpacity)
            store.edit().putString("subtitle_style", o.toString()).apply()
        }

    var picture: PictureSettings
        get() = json("picture")?.let(::pictureFrom) ?: PictureSettings()
        set(value) = store.edit().putString("picture", pictureTo(value).toString()).apply()

    var equalizer: EqualizerSettings
        get() = json("equalizer")?.let(::equalizerFrom) ?: EqualizerSettings()
        set(value) = store.edit().putString("equalizer", equalizerTo(value).toString()).apply()

    var profiles: List<EnhancementProfile>
        get() = try {
            val array = JSONArray(store.getString("profiles", "[]"))
            List(array.length()) { i ->
                val o = array.getJSONObject(i)
                EnhancementProfile(
                    o.getString("name").take(EnhancementProfile.MAX_NAME),
                    pictureFrom(o.getJSONObject("picture")),
                    equalizerFrom(o.getJSONObject("equalizer")),
                )
            }.take(EnhancementProfile.MAX_PROFILES)
        } catch (_: JSONException) {
            emptyList()
        }
        set(value) {
            val array = JSONArray()
            value.take(EnhancementProfile.MAX_PROFILES).forEach { profile ->
                array.put(
                    JSONObject()
                        .put("name", profile.name)
                        .put("picture", pictureTo(profile.picture))
                        .put("equalizer", equalizerTo(profile.equalizer)),
                )
            }
            store.edit().putString("profiles", array.toString()).apply()
        }

    fun resetToDefaults() {
        store.edit().clear().apply()
    }

    private fun json(key: String): JSONObject? = try {
        store.getString(key, null)?.let(::JSONObject)
    } catch (_: JSONException) {
        null
    }

    private fun pictureFrom(o: JSONObject) = PictureSettings(
        o.optDouble("brightness", 1.0).toFloat(),
        o.optDouble("contrast", 1.0).toFloat(),
        o.optDouble("saturation", 1.0).toFloat(),
        o.optDouble("hue", 0.0).toFloat(),
    ).normalized()

    private fun pictureTo(p: PictureSettings) = JSONObject()
        .put("brightness", p.brightness.toDouble())
        .put("contrast", p.contrast.toDouble())
        .put("saturation", p.saturation.toDouble())
        .put("hue", p.hue.toDouble())

    private fun equalizerFrom(o: JSONObject): EqualizerSettings {
        val bands = o.optJSONArray("bands_db")
        return EqualizerSettings(
            o.optBoolean("enabled", false),
            o.optDouble("preamp_db", 0.0).toFloat(),
            List(EqualizerSettings.BAND_COUNT) { (bands?.optDouble(it, 0.0) ?: 0.0).toFloat() },
        ).normalized()
    }

    private fun equalizerTo(e: EqualizerSettings) = JSONObject()
        .put("enabled", e.enabled)
        .put("preamp_db", e.preampDb.toDouble())
        .put("bands_db", JSONArray(e.bandsDb.map { it.toDouble() }))
}
