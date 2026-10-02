package me.vattitude.morningbrief.pipeline

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/** The phone's own default voice: the setting for people who chose it over Kokoro. */
const val PHONE_VOICE = "phone"

/**
 * Who reads the briefing: a Kokoro voice when one is chosen (or nothing is, and the pack is installed),
 * otherwise the phone's own text-to-speech.
 */
interface Narrator {
    /** Saved in the briefing as its voice. */
    val id: String
    val name: String

    suspend fun read(text: String, work: File): Pcm
    fun close()

    companion object {
        /** Returns the narrator and, when the chosen voice couldn't be used, a note saying so. */
        suspend fun open(context: Context, voice: String?, speed: Float): Pair<Narrator, String?> {
            val pack = KokoroPack.current(context)
            val wanted = kokoroVoice(voice) ?: KOKORO_VOICES.first().takeIf { voice == null && pack != null }
            var note: String? = null
            if (wanted != null) {
                if (pack != null) {
                    val kokoro = runCatching {
                        withContext(Dispatchers.Default) { Kokoro.open(pack.dir(context), wanted.british) }
                    }
                    kokoro.getOrNull()?.let { return KokoroNarrator(it, wanted, speed) to null }
                    note = "The natural voice couldn't start (${kokoro.exceptionOrNull()?.message}), so your phone's voice read today's brief."
                } else {
                    note = "The natural voices aren't downloaded, so your phone's voice read today's brief. Download them in Settings."
                }
            }
            val speech = Speech.open(context)
            val name = speech.setVoice(null)
            speech.setSpeed(speed)
            return PhoneNarrator(speech, name) to note
        }
    }
}

private class KokoroNarrator(private val kokoro: Kokoro, private val voice: KokoroVoice, private val speed: Float) : Narrator {
    override val id = voice.id
    override val name = voice.name
    override suspend fun read(text: String, work: File): Pcm = withContext(Dispatchers.Default) { kokoro.generate(text, voice, speed) }
    override fun close() = kokoro.close()
}

private class PhoneNarrator(private val speech: Speech, voiceName: String?) : Narrator {
    override val id = voiceName ?: "default"
    override val name = voiceName ?: "Phone default"
    private var n = 0

    override suspend fun read(text: String, work: File): Pcm {
        val wav = File(work, "${n++}.wav")
        speech.toFile(text, wav)
        return readWav(wav).also { wav.delete() }
    }

    override fun close() = speech.close()
}
