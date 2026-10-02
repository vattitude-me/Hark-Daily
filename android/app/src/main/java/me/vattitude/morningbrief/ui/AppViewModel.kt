package me.vattitude.morningbrief.ui

import android.app.Application
import android.content.ComponentName
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.MoreExecutors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.guava.await
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import me.vattitude.morningbrief.MorningBriefApp
import me.vattitude.morningbrief.data.Settings
import me.vattitude.morningbrief.pipeline.Kokoro
import me.vattitude.morningbrief.pipeline.KokoroPack
import me.vattitude.morningbrief.pipeline.PHONE_VOICE
import me.vattitude.morningbrief.pipeline.Place
import me.vattitude.morningbrief.pipeline.Source
import me.vattitude.morningbrief.pipeline.Speech
import me.vattitude.morningbrief.pipeline.VoiceOption
import me.vattitude.morningbrief.pipeline.kokoroVoice
import me.vattitude.morningbrief.pipeline.searchPlaces
import me.vattitude.morningbrief.playback.PlaybackService
import me.vattitude.morningbrief.work.BuildState
import me.vattitude.morningbrief.work.Scheduler
import me.vattitude.morningbrief.work.VoicePackWorker
import java.time.LocalDate

enum class Tab { Today, Sources, Settings }

data class PlayerState(val date: String? = null, val playing: Boolean = false, val position: Double = 0.0, val ready: Boolean = false)

data class SignIn(val busy: Boolean = false, val error: String? = null)

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = (app as MorningBriefApp).repo

    val tab = MutableStateFlow(Tab.Today)
    val message = MutableStateFlow<String?>(null)

    /** What's saved, and the Settings screen's draft; the draft is only kept once Save is tapped. */
    private val _saved = MutableStateFlow(repo.settings)
    val saved: StateFlow<Settings> = _saved
    private val _settings = MutableStateFlow(repo.settings)
    val settings: StateFlow<Settings> = _settings
    val signedInEmail = MutableStateFlow(repo.email)

    val dates = MutableStateFlow<List<String>>(emptyList())
    val selected = MutableStateFlow<String?>(null)
    val briefing = MutableStateFlow<Briefing?>(null)
    val build: StateFlow<BuildState.Progress> = BuildState.progress

    val player = MutableStateFlow(PlayerState())
    private var controller: MediaController? = null
    private var ticker: Job? = null

    val sources = MutableStateFlow<List<Source>>(emptyList())
    val sourcesNote = MutableStateFlow<String?>(null)
    val sourcesBusy = MutableStateFlow(false)
    val sharedUrl = MutableStateFlow<String?>(null)

    val voices = MutableStateFlow<List<VoiceOption>>(emptyList())
    val voiceEngine = MutableStateFlow("")
    private var preview: Speech? = null

    val packInstalled = MutableStateFlow(KokoroPack.installed(app))
    val packDownload: StateFlow<VoicePackWorker.State> = VoicePackWorker.state
    /** The voice whose sample is being prepared, for a spinner. */
    val previewing = MutableStateFlow<String?>(null)
    private var kokoro: Pair<Boolean, Kokoro>? = null
    private var sample: AudioTrack? = null
    private var sampleJob: Job? = null

    val signIn = MutableStateFlow(SignIn())

    init {
        refreshBriefings()
        viewModelScope.launch {
            var wasRunning = BuildState.progress.value.running
            BuildState.progress.collect {
                if (wasRunning && !it.running) refreshBriefings(selectLatest = true)
                wasRunning = it.running
            }
        }
        viewModelScope.launch {
            VoicePackWorker.state.collect {
                if (it.done) {
                    packInstalled.value = true
                    refreshSaved()
                }
            }
        }
    }

    // ---- Lifecycle ------------------------------------------------------------------------

    fun onOpen() {
        val today = LocalDate.now().toString()
        Scheduler.catchUp(getApplication(), repo.settings, repo.briefings.load(today) != null,
            repo.prefs.lastBuild.optString("day").ifEmpty { null })
        refreshBriefings()
        connectPlayer()
        packInstalled.value = KokoroPack.installed(getApplication())
        viewModelScope.launch {
            repo.pullSettings()
            refreshSaved()
        }
    }

    fun onClose() {
        ticker?.cancel()
        controller?.release()
        controller = null
        stopSample()
        releaseKokoro()
    }

    /** Off the main thread: closing waits for a sample that's still being generated. */
    private fun releaseKokoro() {
        kokoro?.second?.let { k -> Thread { k.close() }.start() }
        kokoro = null
    }

    override fun onCleared() {
        onClose()
        preview?.close()
    }

    // ---- Briefings and playback -----------------------------------------------------------

    fun refreshBriefings(selectLatest: Boolean = false) {
        val list = repo.briefings.dates()
        dates.value = list
        val keep = selected.value?.takeIf { it in list && !selectLatest }
        select(keep ?: list.firstOrNull())
    }

    fun select(date: String?) {
        selected.value = date
        briefing.value = date?.let { repo.briefings.load(it) }?.let { Briefing.from(it) }
    }

    fun buildNow() {
        Scheduler.buildNow(getApplication())
    }

    private fun connectPlayer() {
        if (controller != null) return
        val ctx = getApplication<Application>()
        viewModelScope.launch {
            val c = runCatching {
                MediaController.Builder(ctx, SessionToken(ctx, ComponentName(ctx, PlaybackService::class.java)))
                    .buildAsync().await()
            }.getOrNull() ?: return@launch
            controller = c
            c.addListener(object : Player.Listener {
                override fun onEvents(player: Player, events: Player.Events) = tick()
            })
            tick()
            ticker = viewModelScope.launch {
                while (isActive) {
                    tick()
                    delay(250)
                }
            }
        }
    }

    private fun tick() {
        val c = controller ?: return
        player.value = PlayerState(
            date = c.currentMediaItem?.mediaId,
            playing = c.isPlaying,
            position = c.currentPosition / 1000.0,
            ready = true,
        )
    }

    /** Loads [date] into the player if it isn't already there. */
    private fun load(date: String): MediaController? {
        val c = controller ?: return null
        if (c.currentMediaItem?.mediaId != date) {
            val b = briefing.value?.takeIf { it.date == date } ?: repo.briefings.load(date)?.let { Briefing.from(it) }
            val item = MediaItem.Builder()
                .setMediaId(date)
                .setUri(Uri.fromFile(repo.briefings.audio(date)))
                .setMediaMetadata(MediaMetadata.Builder().setTitle(b?.title ?: date).setArtist("Morning Brief").build())
                .build()
            c.setMediaItem(item)
            c.prepare()
        }
        return c
    }

    fun togglePlay() {
        val date = selected.value ?: return
        val c = load(date) ?: return
        if (c.isPlaying) c.pause() else c.play()
        tick()
    }

    fun seekTo(seconds: Double, play: Boolean = true) {
        val date = selected.value ?: return
        val c = load(date) ?: return
        c.seekTo((seconds * 1000).toLong().coerceAtLeast(0))
        if (play) c.play()
        tick()
    }

    fun skip(seconds: Int) {
        val c = controller ?: return
        if (c.currentMediaItem == null) return
        c.seekTo((c.currentPosition + seconds * 1000L).coerceAtLeast(0))
        tick()
    }

    // ---- Sources -----------------------------------------------------------------------------

    fun loadSources() {
        viewModelScope.launch {
            sourcesBusy.value = true
            val (list, note) = repo.sources()
            sources.value = list
            sourcesNote.value = note
            sourcesBusy.value = false
        }
    }

    fun setEnabled(source: Source, enabled: Boolean) {
        sources.value = sources.value.map { if (it.id == source.id && it.url == source.url) it.copy(enabled = enabled) else it }
        viewModelScope.launch {
            repo.setEnabled(source, enabled)?.let { message.value = it }
            refreshSaved()
            loadSources()
        }
    }

    suspend fun addSource(url: String, section: String): String? = try {
        val found = repo.addSource(url, section)
        loadSources()
        sharedUrl.value = null
        val what = when (found.kind) {
            "feed" -> "a news feed"
            "page" -> "a page of links"
            else -> "a single article (read once)"
        }
        message.value = "Added ${found.name.ifBlank { "the link" }} as $what."
        null
    } catch (e: Exception) {
        e.message ?: "That link couldn't be added."
    }

    fun removeSource(source: Source) {
        viewModelScope.launch {
            runCatching { repo.removeSource(source) }.exceptionOrNull()?.let { message.value = it.message }
            loadSources()
        }
    }

    fun shared(url: String) {
        sharedUrl.value = url
        tab.value = Tab.Sources
    }

    // ---- Settings -----------------------------------------------------------------------------

    /** Changes the draft; nothing is kept until [save]. */
    fun update(change: (Settings) -> Settings) {
        _settings.value = change(_settings.value)
    }

    fun save() {
        val new = _settings.value
        viewModelScope.launch {
            val old = repo.settings
            val problem = repo.saveSettings(new)
            if (old.daily != new.daily || old.readyBy != new.readyBy) Scheduler.schedule(getApplication(), new)
            _saved.value = repo.settings
            message.value = problem ?: "Settings saved"
        }
    }

    fun discard() {
        _settings.value = _saved.value
    }

    /** Takes in changes saved elsewhere (sync, source switches, a finished download) without losing the draft. */
    private fun refreshSaved() {
        val before = _saved.value
        val now = repo.settings
        _saved.value = now
        _settings.value = if (_settings.value == before) now
        else _settings.value.copy(disabledSources = now.disabledSources, disabledUrls = now.disabledUrls)
    }

    suspend fun places(query: String): List<Place> = withContext(Dispatchers.IO) { searchPlaces(query) }

    fun loadVoices() {
        packInstalled.value = KokoroPack.installed(getApplication())
        viewModelScope.launch {
            val s = preview ?: runCatching { Speech.open(getApplication()) }.getOrNull()?.also { preview = it }
            if (s == null) {
                voices.value = emptyList()
                return@launch
            }
            voices.value = s.voices()
            voiceEngine.value = s.engine
        }
    }

    fun downloadVoices() = VoicePackWorker.start(getApplication())

    fun cancelDownload() = VoicePackWorker.cancel(getApplication())

    fun removeVoices() {
        stopSample()
        releaseKokoro()
        KokoroPack.remove(getApplication())
        packInstalled.value = false
        viewModelScope.launch {
            val st = repo.settings
            if (kokoroVoice(st.voice) != null) repo.saveSettings(st.copy(voice = PHONE_VOICE))
            refreshSaved()
            if (kokoroVoice(_settings.value.voice) != null) _settings.value = _settings.value.copy(voice = PHONE_VOICE)
            message.value = "Natural voices removed"
        }
    }

    fun packSize(): Long = KokoroPack.sizeOnDisk(getApplication())

    /** Plays a short greeting in [voice]: Kokoro voices are generated here, phone voices spoken directly. */
    fun previewVoice(voice: String?) {
        stopSample()
        preview?.stop()
        val speed = settings.value.speed
        val who = settings.value.name.trim().ifEmpty { null }
        val line = "Good morning${who?.let { ", $it" } ?: ""}! Here's your briefing for today, starting with the top stories."
        val k = kokoroVoice(voice)
        if (k == null || !packInstalled.value) {
            val s = preview ?: return
            s.setVoice(voice?.takeIf { it != PHONE_VOICE && kokoroVoice(it) == null })
            s.setSpeed(speed)
            s.speak(line)
            return
        }
        previewing.value = k.id
        sampleJob = viewModelScope.launch {
            try {
                val pcm = withContext(Dispatchers.Default) {
                    val engine = kokoro?.takeIf { it.first == k.british }?.second ?: run {
                        releaseKokoro()
                        Kokoro.open(KokoroPack.dir(getApplication()), k.british).also { kokoro = k.british to it }
                    }
                    engine.generate(line, k, speed)
                }
                play(pcm.samples, pcm.rate)
            } catch (e: Exception) {
                if (e !is kotlinx.coroutines.CancellationException) message.value = "Couldn't play the sample: ${e.message}"
            } finally {
                previewing.value = null
            }
        }
    }

    private fun play(samples: FloatArray, rate: Int) {
        if (samples.isEmpty()) return
        val track = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setAudioFormat(AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_FLOAT).setSampleRate(rate)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(samples.size * 4)
            .build()
        track.write(samples, 0, samples.size, AudioTrack.WRITE_BLOCKING)
        track.play()
        sample = track
    }

    private fun stopSample() {
        sampleJob?.cancel()
        sample?.let { runCatching { it.stop() }; it.release() }
        sample = null
    }

    /** The web app's Google sign-in page; Google sends people back to the app's own link, handled by [finishGoogle]. */
    fun googleSignInUrl(): Uri = repo.supabase.googleUrl("${getApplication<Application>().packageName}://auth")

    fun finishGoogle(callback: Uri) {
        signIn.value = SignIn(busy = true)
        viewModelScope.launch {
            runCatching { repo.supabase.finishGoogle(callback) }.onSuccess { signedIn() }.onFailure {
                signIn.value = SignIn(error = it.message)
            }
        }
    }

    private suspend fun signedIn() {
        signIn.value = SignIn()
        signedInEmail.value = repo.email
        repo.pullSettings()
        refreshSaved()
        loadSources()
        message.value = "Signed in. Your sources and settings now match the web app."
    }

    fun signOut() {
        repo.supabase.signOut()
        signedInEmail.value = null
        loadSources()
    }
}
