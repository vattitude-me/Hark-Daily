package me.vattitude.morningbrief.ui

import android.app.Application
import android.content.ComponentName
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
import me.vattitude.morningbrief.pipeline.Place
import me.vattitude.morningbrief.pipeline.Source
import me.vattitude.morningbrief.pipeline.Speech
import me.vattitude.morningbrief.pipeline.VoiceOption
import me.vattitude.morningbrief.pipeline.searchPlaces
import me.vattitude.morningbrief.playback.PlaybackService
import me.vattitude.morningbrief.work.BuildState
import me.vattitude.morningbrief.work.Scheduler
import java.time.LocalDate

enum class Tab { Today, Sources, Settings }

data class PlayerState(val date: String? = null, val playing: Boolean = false, val position: Double = 0.0, val ready: Boolean = false)

data class SignIn(val email: String = "", val codeSent: Boolean = false, val busy: Boolean = false, val error: String? = null)

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = (app as MorningBriefApp).repo

    val tab = MutableStateFlow(Tab.Today)
    val message = MutableStateFlow<String?>(null)

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
    }

    // ---- Lifecycle ------------------------------------------------------------------------

    fun onOpen() {
        val today = LocalDate.now().toString()
        Scheduler.catchUp(getApplication(), repo.settings, repo.briefings.load(today) != null,
            repo.prefs.lastBuild.optString("day").ifEmpty { null })
        refreshBriefings()
        connectPlayer()
        viewModelScope.launch {
            repo.pullSettings()
            _settings.value = repo.settings
        }
    }

    fun onClose() {
        ticker?.cancel()
        controller?.release()
        controller = null
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
            _settings.value = repo.settings
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

    private var saving: Job? = null

    /** Shows the change at once; saves (and syncs) once typing or dragging pauses. */
    fun update(change: (Settings) -> Settings) {
        val new = change(_settings.value)
        _settings.value = new
        saving?.cancel()
        saving = viewModelScope.launch {
            delay(600)
            val old = repo.settings
            repo.saveSettings(new)?.let { message.value = it }
            if (old.daily != new.daily || old.readyBy != new.readyBy) Scheduler.schedule(getApplication(), new)
        }
    }

    suspend fun places(query: String): List<Place> = withContext(Dispatchers.IO) { searchPlaces(query) }

    fun loadVoices() {
        viewModelScope.launch {
            val s = preview ?: runCatching { Speech.open(getApplication()) }.getOrNull()?.also { preview = it }
            if (s == null) {
                message.value = "This phone has no text-to-speech engine. Install Speech Services by Google."
                return@launch
            }
            voices.value = s.voices()
            voiceEngine.value = s.engine
        }
    }

    fun previewVoice(name: String?) {
        val s = preview ?: return
        s.stop()
        s.setVoice(name)
        s.setSpeed(settings.value.speed)
        val who = settings.value.name.trim().ifEmpty { null }
        s.speak("Good morning${who?.let { ", $it" } ?: ""}! Here's your briefing for today.")
    }

    fun sendCode(email: String) {
        signIn.value = SignIn(email = email, busy = true)
        viewModelScope.launch {
            signIn.value = runCatching { repo.supabase.sendCode(email.trim()) }.fold(
                { SignIn(email = email, codeSent = true) },
                { SignIn(email = email, error = it.message) },
            )
        }
    }

    fun verify(code: String) {
        val email = signIn.value.email
        signIn.value = signIn.value.copy(busy = true, error = null)
        viewModelScope.launch {
            runCatching { repo.supabase.verify(email.trim(), code) }.onSuccess {
                signIn.value = SignIn()
                signedInEmail.value = repo.email
                repo.pullSettings()
                _settings.value = repo.settings
                loadSources()
                message.value = "Signed in. Your sources and settings now match the web app."
            }.onFailure {
                signIn.value = signIn.value.copy(busy = false, error = it.message)
            }
        }
    }

    fun cancelSignIn() {
        signIn.value = SignIn()
    }

    fun signOut() {
        repo.supabase.signOut()
        signedInEmail.value = null
        loadSources()
    }
}
