package me.vattitude.morningbrief.pipeline

import android.content.Context
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.io.File
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

const val GOOGLE_TTS = "com.google.android.tts"

/** A voice the briefing can use. [needsDownload] voices are listed but must be installed first. */
/**
 * The phone's text-to-speech engine. Each script segment is rendered to a WAV file with
 * synthesizeToFile(), then stitched, the same "voice each segment, then join" approach the server uses.
 */
class Speech private constructor(private val tts: TextToSpeech) {
    private val pending = ConcurrentHashMap<String, CompletableDeferred<Unit>>()
    private val counter = AtomicInteger()

    init {
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String) {}
            override fun onDone(utteranceId: String) {
                pending.remove(utteranceId)?.complete(Unit)
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String) {
                pending.remove(utteranceId)?.completeExceptionally(IllegalStateException("Speech failed"))
            }

            override fun onError(utteranceId: String, errorCode: Int) {
                pending.remove(utteranceId)?.completeExceptionally(IllegalStateException("Speech failed ($errorCode)"))
            }
        })
    }

    val engine: String get() = tts.defaultEngine ?: ""

    /** Picks the named voice, else the phone's default English one; returns its name. */
    fun setVoice(name: String?): String? {
        val all = runCatching { tts.voices }.getOrNull() ?: emptySet<Voice>()
        val usable = all.filter { offline(it) && TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED !in it.features }
        val chosen = usable.firstOrNull { it.name == name }
            ?: tts.defaultVoice?.takeIf { it in usable }
            ?: usable.sortedWith(compareBy<Voice>({ regionOrder(it.locale) }, { -it.quality })).firstOrNull()
        if (chosen != null) tts.voice = chosen else tts.language = Locale.CANADA
        return chosen?.name
    }

    /** English voices that run on the phone. Google also lists a "-network" twin of each, which needs a connection. */
    private fun offline(v: Voice) = v.locale.language == "en" && !v.name.endsWith("-network") &&
        TextToSpeech.Engine.KEY_FEATURE_NETWORK_SYNTHESIS !in v.features

    fun setSpeed(speed: Float) {
        tts.setSpeechRate(speed)
    }

    suspend fun toFile(text: String, file: File) {
        val id = "seg-${counter.incrementAndGet()}"
        val done = CompletableDeferred<Unit>()
        pending[id] = done
        val clipped = text.take(TextToSpeech.getMaxSpeechInputLength() - 1)
        val result = tts.synthesizeToFile(clipped, Bundle(), file, id)
        if (result != TextToSpeech.SUCCESS) {
            pending.remove(id)
            throw IllegalStateException("The voice engine refused the text")
        }
        withTimeout(90_000) { done.await() }
    }

    fun speak(text: String) {
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "preview")
    }

    fun stop() {
        tts.stop()
    }

    fun close() {
        tts.shutdown()
    }

    companion object {
        /** Prefers Speech Services by Google when it's installed: on Samsung and others the default engine is the maker's. */
        suspend fun open(context: Context): Speech = withContext(Dispatchers.Main) {
            val hasGoogle = runCatching { context.packageManager.getPackageInfo(GOOGLE_TTS, 0) }.isSuccess
            val ready = CompletableDeferred<Int>()
            val tts = if (hasGoogle) {
                TextToSpeech(context.applicationContext, { ready.complete(it) }, GOOGLE_TTS)
            } else {
                TextToSpeech(context.applicationContext) { ready.complete(it) }
            }
            val status = withTimeout(20_000) { ready.await() }
            if (status != TextToSpeech.SUCCESS) {
                tts.shutdown()
                throw IllegalStateException("The phone's text-to-speech engine isn't available")
            }
            Speech(tts)
        }

        private fun regionOrder(locale: Locale) = when (locale.country) {
            "CA" -> 0
            "US" -> 1
            "GB" -> 2
            "AU" -> 3
            else -> 4
        }
    }
}
