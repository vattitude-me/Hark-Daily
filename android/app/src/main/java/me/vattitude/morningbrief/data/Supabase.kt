package me.vattitude.morningbrief.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import me.vattitude.morningbrief.pipeline.Source
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/** The same public settings as web/config.js: the publishable key is safe to ship, row-level security does the rest. */
const val SUPABASE_URL = "https://oohbmeffdncyzujmeqcz.supabase.co"
const val SUPABASE_KEY = "sb_publishable_HgWQGelTuCEU6ayqFdY4Cg_F_-VVEYv"

data class Session(val accessToken: String, val refreshToken: String, val expiresAt: Long, val userId: String, val email: String) {
    fun toJson(): JSONObject = JSONObject().put("access_token", accessToken).put("refresh_token", refreshToken)
        .put("expires_at", expiresAt).put("user_id", userId).put("email", email)

    companion object {
        fun fromJson(j: JSONObject) = Session(j.getString("access_token"), j.getString("refresh_token"),
            j.getLong("expires_at"), j.getString("user_id"), j.getString("email"))
    }
}

class SupabaseError(message: String, val status: Int = 0) : Exception(message)

/**
 * Sign-in (email code) and the sources/profiles tables, over plain REST.
 * The app never touches briefings or storage: briefings are built and kept on the phone.
 */
class Supabase(private val prefs: Prefs) {
    private val client = OkHttpClient.Builder().callTimeout(20, TimeUnit.SECONDS).build()
    private val json = "application/json".toMediaType()

    val session: Session? get() = prefs.session

    suspend fun sendCode(email: String) {
        call("POST", "/auth/v1/otp", JSONObject().put("email", email).put("create_user", true), auth = false)
    }

    suspend fun verify(email: String, code: String): Session {
        val body = JSONObject().put("type", "email").put("email", email).put("token", code.trim())
        val res = call("POST", "/auth/v1/verify", body, auth = false) as JSONObject
        return saveSession(res)
    }

    fun signOut() {
        prefs.session = null
    }

    suspend fun profileSettings(): JSONObject {
        val s = fresh()
        val rows = call("GET", "/rest/v1/profiles?select=settings&id=eq.${s.userId}") as JSONArray
        return rows.optJSONObject(0)?.optJSONObject("settings") ?: JSONObject()
    }

    /** Merges the shared fields into the stored settings, leaving the web app's own (voice, daily...) alone. */
    suspend fun saveSettings(shared: JSONObject) {
        val s = fresh()
        val merged = profileSettings()
        for (key in shared.keys()) merged.put(key, shared.get(key))
        call("PATCH", "/rest/v1/profiles?id=eq.${s.userId}", JSONObject().put("settings", merged))
    }

    suspend fun sources(): List<Source> {
        fresh()
        val rows = call("GET", "/rest/v1/sources?select=*&order=id") as JSONArray
        return (0 until rows.length()).map { sourceFrom(rows.getJSONObject(it)) }
    }

    suspend fun addSource(url: String, section: String, name: String): Source {
        val s = fresh()
        val body = JSONObject().put("user_id", s.userId).put("url", url).put("section", section).put("name", name)
        val rows = call("POST", "/rest/v1/sources?select=*", body, prefer = "return=representation") as JSONArray
        return sourceFrom(rows.getJSONObject(0))
    }

    suspend fun updateSource(id: Long, values: JSONObject) {
        fresh()
        call("PATCH", "/rest/v1/sources?id=eq.$id", values)
    }

    suspend fun deleteSource(id: Long) {
        fresh()
        call("DELETE", "/rest/v1/sources?id=eq.$id")
    }

    private fun sourceFrom(j: JSONObject) = Source(
        id = j.getLong("id"),
        name = j.optString("name"),
        url = j.optString("url"),
        section = j.optString("section", "custom"),
        weight = j.optDouble("weight", 1.0),
        kind = j.optString("kind", "auto"),
        feedUrl = j.optString("feed_url").takeIf { it.isNotEmpty() && it != "null" },
        enabled = j.optBoolean("enabled", true),
        builtin = j.isNull("user_id"),
    )

    /** The current session, refreshed when it's about to expire. */
    private suspend fun fresh(): Session {
        val s = prefs.session ?: throw SupabaseError("Please sign in again.", 401)
        if (s.expiresAt - 60 > System.currentTimeMillis() / 1000) return s
        val res = try {
            call("POST", "/auth/v1/token?grant_type=refresh_token", JSONObject().put("refresh_token", s.refreshToken), auth = false)
        } catch (e: SupabaseError) {
            if (e.status in 400..499) prefs.session = null
            throw e
        }
        return saveSession(res as JSONObject)
    }

    private fun saveSession(res: JSONObject): Session {
        val user = res.getJSONObject("user")
        val session = Session(
            accessToken = res.getString("access_token"),
            refreshToken = res.getString("refresh_token"),
            expiresAt = res.optLong("expires_at", System.currentTimeMillis() / 1000 + res.optLong("expires_in", 3600)),
            userId = user.getString("id"),
            email = user.optString("email"),
        )
        prefs.session = session
        return session
    }

    private suspend fun call(method: String, path: String, body: JSONObject? = null, auth: Boolean = true,
                             prefer: String? = null): Any? = withContext(Dispatchers.IO) {
        val builder = Request.Builder().url(SUPABASE_URL + path).header("apikey", SUPABASE_KEY)
        if (auth) prefs.session?.let { builder.header("Authorization", "Bearer ${it.accessToken}") }
        prefer?.let { builder.header("Prefer", it) }
        val payload = body?.toString()?.toRequestBody(json)
        builder.method(method, payload ?: if (method == "GET" || method == "DELETE") null else "".toRequestBody(json))
        val (code, text) = try {
            client.newCall(builder.build()).execute().use { it.code to (it.body?.string() ?: "") }
        } catch (e: IOException) {
            throw SupabaseError("You're offline or the service can't be reached.")
        }
        if (code >= 400) throw SupabaseError(friendly(text), code)
        val trimmed = text.trim()
        when {
            trimmed.startsWith("[") -> JSONArray(trimmed)
            trimmed.startsWith("{") -> JSONObject(trimmed)
            else -> null
        }
    }

    private fun friendly(raw: String): String {
        val msg = runCatching {
            val j = JSONObject(raw)
            j.optString("msg").ifEmpty { j.optString("message") }.ifEmpty { j.optString("error_description") }
        }.getOrNull().orEmpty().ifEmpty { raw.take(200) }
        return when {
            Regex("row-level security.*sources", RegexOption.IGNORE_CASE).containsMatchIn(msg) ->
                "You can have up to 25 links. Remove one to add another."
            Regex("duplicate key.*sources", RegexOption.IGNORE_CASE).containsMatchIn(msg) -> "You've already added that link."
            Regex("expired|invalid", RegexOption.IGNORE_CASE).containsMatchIn(msg) && "token" in msg.lowercase() ->
                "That code didn't work. Check it, or ask for a new one."
            else -> msg
        }
    }
}
