package me.vattitude.morningbrief.pipeline

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.MediaMuxer
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sqrt
import kotlin.math.tanh

/** A port of app/audio.py: clean up each voice clip and stitch them into one AAC file with chapter marks. */

const val SAMPLE_RATE = 24_000

class Pcm(val samples: FloatArray, val rate: Int)

/** Reads the 16-bit (or float) PCM WAV that synthesizeToFile() writes; stereo is mixed down. */
fun readWav(file: File): Pcm {
    val bytes = file.readBytes()
    val buf = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
    require(bytes.size > 12 && String(bytes, 0, 4) == "RIFF" && String(bytes, 8, 4) == "WAVE") { "Not a WAV file" }
    var pos = 12
    var format = 1
    var channels = 1
    var rate = SAMPLE_RATE
    var bits = 16
    while (pos + 8 <= bytes.size) {
        val id = String(bytes, pos, 4)
        var size = buf.getInt(pos + 4)
        val start = pos + 8
        if (id == "fmt ") {
            format = buf.getShort(start).toInt()
            channels = buf.getShort(start + 2).toInt()
            rate = buf.getInt(start + 4)
            bits = buf.getShort(start + 14).toInt()
        } else if (id == "data") {
            // Streaming engines may leave the size as 0 or -1: use what's actually there.
            if (size <= 0 || start + size > bytes.size) size = bytes.size - start
            val frame = channels * bits / 8
            val n = size / frame
            val out = FloatArray(n)
            for (i in 0 until n) {
                var sum = 0f
                for (c in 0 until channels) {
                    val at = start + i * frame + c * bits / 8
                    sum += if (format == 3 && bits == 32) buf.getFloat(at) else buf.getShort(at) / 32768f
                }
                out[i] = sum / channels
            }
            return Pcm(out, rate)
        }
        pos = start + size + (size and 1)
    }
    return Pcm(FloatArray(0), rate)
}

fun resample(samples: FloatArray, src: Int, dst: Int): FloatArray {
    if (src == dst || samples.isEmpty()) return samples
    val n = (samples.size.toLong() * dst / src).toInt()
    val out = FloatArray(n)
    val step = samples.size.toDouble() / n
    for (i in 0 until n) {
        val x = i * step
        val j = x.toInt()
        val frac = (x - j).toFloat()
        val a = samples[j]
        val b = if (j + 1 < samples.size) samples[j + 1] else a
        out[i] = a + (b - a) * frac
    }
    return out
}

fun trimSilence(samples: FloatArray, threshold: Float = 0.004f, pad: Double = 0.05, rate: Int = SAMPLE_RATE): FloatArray {
    val first = samples.indexOfFirst { abs(it) > threshold }
    if (first < 0) return samples
    val last = samples.indexOfLast { abs(it) > threshold }
    val p = (pad * rate).toInt()
    return samples.copyOfRange(maxOf(first - p, 0), min(last + p, samples.size))
}

/** Even out loudness between segments, with a soft limiter so peaks never clip. */
fun level(samples: FloatArray, targetRms: Float = 0.085f): FloatArray {
    if (samples.isEmpty()) return samples
    var sum = 0.0
    for (s in samples) sum += s * s
    val rms = sqrt(sum / samples.size).toFloat()
    val gain = if (rms > 1e-5f) targetRms / rms else 1f
    val norm = tanh(1.2f)
    return FloatArray(samples.size) { tanh(samples[it] * gain * 1.2f) / norm }
}

fun fade(samples: FloatArray, ms: Double = 12.0, rate: Int = SAMPLE_RATE): FloatArray {
    val n = min((rate * ms / 1000).toInt(), samples.size / 2)
    if (n == 0) return samples
    val out = samples.copyOf()
    for (i in 0 until n) {
        val r = i.toFloat() / n
        out[i] *= r
        out[out.size - 1 - i] *= r
    }
    return out
}

fun prepareClip(pcm: Pcm): FloatArray =
    fade(level(trimSilence(resample(pcm.samples, pcm.rate, SAMPLE_RATE))))

/**
 * Streams mono PCM into an AAC-LC .m4a file, so a ten-minute briefing never sits in memory whole.
 * [seconds] is the running length, which gives each chapter its start and end.
 */
class AacWriter(out: File, private val rate: Int = SAMPLE_RATE, bitrate: Int = 64_000) {
    private val codec: MediaCodec
    private val muxer = MediaMuxer(out.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
    private val info = MediaCodec.BufferInfo()
    private var track = -1
    private var started = false
    private var written = 0L

    init {
        val format = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC, rate, 1).apply {
            setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
            setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
            setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16_384)
        }
        codec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC)
        codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        codec.start()
    }

    val seconds: Double get() = written.toDouble() / rate

    fun silence(seconds: Double) = write(FloatArray((seconds * rate).roundToInt()))

    fun write(samples: FloatArray) {
        val bytes = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (s in samples) bytes.putShort((s.coerceIn(-1f, 1f) * 32767).toInt().toShort())
        val pcm = bytes.array()
        var offset = 0
        while (offset < pcm.size) {
            val index = codec.dequeueInputBuffer(10_000)
            if (index >= 0) {
                val input = codec.getInputBuffer(index)!!
                input.clear()
                val n = min(input.remaining(), pcm.size - offset) and 1.inv()
                input.put(pcm, offset, n)
                codec.queueInputBuffer(index, 0, n, written * 1_000_000 / rate, 0)
                offset += n
                written += n / 2
            }
            drain(false)
        }
    }

    fun close() {
        while (true) {
            val index = codec.dequeueInputBuffer(10_000)
            if (index >= 0) {
                codec.queueInputBuffer(index, 0, 0, written * 1_000_000 / rate, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                break
            }
            drain(false)
        }
        drain(true)
        codec.stop()
        codec.release()
        if (started) muxer.stop()
        muxer.release()
    }

    private fun drain(endOfStream: Boolean) {
        while (true) {
            val index = codec.dequeueOutputBuffer(info, if (endOfStream) 10_000 else 0)
            when {
                index == MediaCodec.INFO_TRY_AGAIN_LATER -> if (!endOfStream) return
                index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                    track = muxer.addTrack(codec.outputFormat)
                    muxer.start()
                    started = true
                }
                index >= 0 -> {
                    val output = codec.getOutputBuffer(index)!!
                    if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) info.size = 0
                    if (info.size > 0 && started) {
                        output.position(info.offset)
                        output.limit(info.offset + info.size)
                        muxer.writeSampleData(track, output, info)
                    }
                    codec.releaseOutputBuffer(index, false)
                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) return
                }
            }
        }
    }
}
