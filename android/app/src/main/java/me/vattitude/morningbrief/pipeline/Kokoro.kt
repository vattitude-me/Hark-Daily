package me.vattitude.morningbrief.pipeline

import android.content.Context
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsKokoroModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream
import java.io.File
import java.io.FilterInputStream
import java.io.InputStream
import java.util.concurrent.TimeUnit
import kotlin.coroutines.coroutineContext

/** A Kokoro voice: the same ids the web app saves (kokoro:af_heart), [sid] is its index in the model. */
data class KokoroVoice(val id: String, val name: String, val accent: String, val description: String, val sid: Int) {
    val british: Boolean get() = id.startsWith("kokoro:b")
}

/** The web app's Kokoro voices. Speaker ids follow the model's alphabetical voice list. */
val KOKORO_VOICES = listOf(
    KokoroVoice("kokoro:af_heart", "Heart", "American", "Warm and natural", 3),
    KokoroVoice("kokoro:af_bella", "Bella", "American", "Bright and upbeat", 2),
    KokoroVoice("kokoro:am_michael", "Michael", "American", "Calm, steady newsreader", 16),
    KokoroVoice("kokoro:am_fenrir", "Fenrir", "American", "Deep and confident", 14),
    KokoroVoice("kokoro:am_puck", "Puck", "American", "Friendly, conversational", 18),
    KokoroVoice("kokoro:bf_emma", "Emma", "British", "Polished, BBC-style", 21),
    KokoroVoice("kokoro:bm_george", "George", "British", "Classic, authoritative", 26),
)

fun kokoroVoice(id: String?): KokoroVoice? = KOKORO_VOICES.firstOrNull { it.id == id }

/** Kokoro-82M through sherpa-onnx, fully on the phone once the model is downloaded. */
class Kokoro private constructor(private val tts: OfflineTts) {

    @Synchronized
    fun generate(text: String, voice: KokoroVoice, speed: Float): Pcm {
        val audio = tts.generate(text, sid = voice.sid, speed = speed)
        return Pcm(audio.samples, audio.sampleRate)
    }

    @Synchronized
    fun close() = tts.release()

    companion object {
        /** Loading takes a few seconds; the lexicon follows the voice's accent. */
        fun open(dir: File, british: Boolean): Kokoro {
            val lexicon = File(dir, if (british) "lexicon-gb-en.txt" else "lexicon-us-en.txt")
            val config = OfflineTtsConfig(
                model = OfflineTtsModelConfig(
                    kokoro = OfflineTtsKokoroModelConfig(
                        model = File(dir, "model.onnx").path,
                        voices = File(dir, "voices.bin").path,
                        tokens = File(dir, "tokens.txt").path,
                        dataDir = File(dir, "espeak-ng-data").path,
                        lexicon = lexicon.path,
                        lang = if (british) "en-gb" else "en-us",
                    ),
                    numThreads = Runtime.getRuntime().availableProcessors().coerceIn(1, 4),
                ),
            )
            return Kokoro(OfflineTts(config = config))
        }
    }
}

/**
 * The optional voice download: sherpa-onnx's int8 build of Kokoro v1.0 (about 130 MB). Only the English
 * files are kept. It's unpacked into a temporary folder and only moved into place once complete.
 */
object KokoroPack {
    const val URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-int8-multi-lang-v1_0.tar.bz2"
    const val DOWNLOAD_BYTES = 132_303_094L
    private const val READY = ".ready"

    fun dir(context: Context) = File(context.filesDir, "voices/kokoro-v1_0")
    fun installed(context: Context) = File(dir(context), READY).exists()

    fun sizeOnDisk(context: Context): Long = dir(context).walkBottomUp().filter { it.isFile }.sumOf { it.length() }

    fun remove(context: Context) {
        dir(context).deleteRecursively()
    }

    /** Streams the archive straight into the voice folder; [progress] gets 0..1 of the download. */
    suspend fun install(context: Context, progress: (Float) -> Unit) = withContext(Dispatchers.IO) {
        val job = coroutineContext[Job]
        val target = dir(context)
        val tmp = File(target.parentFile, "kokoro-v1_0.part").apply { deleteRecursively(); mkdirs() }
        val client = OkHttpClient.Builder().connectTimeout(30, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS).build()
        try {
            client.newCall(Request.Builder().url(URL).build()).execute().use { resp ->
                if (!resp.isSuccessful) throw IllegalStateException("Download failed (HTTP ${resp.code})")
                val body = resp.body ?: throw IllegalStateException("Download failed")
                val total = body.contentLength().takeIf { it > 0 } ?: DOWNLOAD_BYTES
                val counted = Counting(body.byteStream(), job) { read -> progress((read.toFloat() / total).coerceIn(0f, 1f)) }
                TarArchiveInputStream(BZip2CompressorInputStream(counted.buffered(1 shl 16))).use { tar ->
                    while (true) {
                        val entry = tar.nextEntry ?: break
                        if (!entry.isFile) continue
                        val rel = keep(entry.name.substringAfter('/')) ?: continue
                        val out = File(tmp, rel).canonicalFile
                        require(out.path.startsWith(tmp.canonicalPath)) { "Bad path in archive" }
                        out.parentFile?.mkdirs()
                        out.outputStream().use { tar.copyTo(it, 1 shl 16) }
                    }
                }
            }
            for (name in listOf("model.onnx", "voices.bin", "tokens.txt", "lexicon-us-en.txt", "espeak-ng-data")) {
                if (!File(tmp, name).exists()) throw IllegalStateException("The voice download was incomplete ($name)")
            }
            File(tmp, READY).writeText("kokoro-int8-multi-lang-v1_0")
            target.deleteRecursively()
            if (!tmp.renameTo(target)) throw IllegalStateException("Couldn't save the voices")
        } finally {
            tmp.deleteRecursively()
        }
    }

    /** The files an English briefing needs, renamed where the archive's names vary. */
    private fun keep(rel: String): String? = when {
        rel.endsWith(".onnx") && '/' !in rel -> "model.onnx"
        rel in setOf("voices.bin", "tokens.txt", "lexicon-us-en.txt", "lexicon-gb-en.txt") -> rel
        rel.startsWith("espeak-ng-data/") -> rel
        else -> null
    }

    /** Reports bytes read, and stops a cancelled download at the next read. */
    private class Counting(input: InputStream, private val job: Job?, private val report: (Long) -> Unit) : FilterInputStream(input) {
        private var read = 0L
        private var reported = 0L

        private fun count(n: Int) {
            if (job?.isActive == false) throw CancellationException("Download cancelled")
            if (n > 0) read += n
            if (read - reported > 512 * 1024) {
                reported = read
                report(read)
            }
        }

        override fun read(): Int = super.read().also { if (it >= 0) count(1) else count(0) }
        override fun read(b: ByteArray, off: Int, len: Int): Int = super.read(b, off, len).also { count(it) }
    }
}
