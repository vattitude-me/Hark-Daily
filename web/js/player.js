// Audio player: APK-style hero with segmented progress, chapters, lock-screen
// controls and resume.
//
// Two sources are supported:
//   * one file per briefing (briefing.audio_url) — the on-device build;
//   * a playlist of shared daily clips (briefing.clips[]) — the single-source pack,
//     played back to back with the next clip pre-buffered so the joins are seamless.
import { fmtTime, h, store } from './api.js';
import { parseDialogueTurns } from './storypack.js';

export function splitSentences(text) {
  if (!text) return [];
  const clean = text.trim();
  if (!clean) return [];
  if (typeof Intl !== 'undefined' && Intl.Segmenter) {
    try {
      const segmenter = new Intl.Segmenter('en', { granularity: 'sentence' });
      const parts = Array.from(segmenter.segment(clean), (s) => s.segment.trim()).filter(Boolean);
      if (parts.length) return parts;
    } catch { /* fallback below */ }
  }
  const parts = clean.split(/(?<=[.!?]["'”’»)]?)\s+(?=[A-Z0-9"'“‘])/).map((s) => s.trim()).filter(Boolean);
  return parts.length ? parts : [clean];
}

/** Where a briefing's playback position is remembered: each edition has its own timeline. */
export const posKeyFor = (b) => {
  const ed = b?.edition || 'ca';
  return b?.mode && b.mode !== 'full' ? `pos-${b?.date}-${b?.mode}-${ed}` : `pos-${b?.date}-${ed}`;
};

export class Player extends EventTarget {
  constructor() {
    super();
    // Dual persistent in-DOM audio elements for seamless background baton-pass handoff.
    // Together with silentAnchor, this ensures iOS WebKit and Android Chrome never revoke
    // playback privileges or suspend the JavaScript background thread between clips.
    const hasDoc = typeof document !== 'undefined';
    this.audioA = (hasDoc && document.getElementById('audio')) || (typeof Audio !== 'undefined' ? new Audio() : null);
    this.audioB = (hasDoc && document.getElementById('audioB')) || (typeof Audio !== 'undefined' ? new Audio() : null);
    this.silentAnchor = (hasDoc && document.getElementById('silentAnchor')) || null;
    this.activeAudio = this.audioA;
    this.standbyAudio = this.audioB;
    this.handingOff = false;
    this.preloadReady = false;
    this.isPrimed = false;
    this.wakeLock = null;

    if (this.audioA) this.audioA.preload = 'auto';
    if (this.audioB) this.audioB.preload = 'auto';

    this.clips = null;
    this.index = 0;
    this.hero = hasDoc ? document.getElementById('hero') : null;
    this.heroInView = true;
    this.el = hasDoc ? {
      play: document.getElementById('playBtn'),
      prev: document.getElementById('prevChapter'),
      next: document.getElementById('nextChapter'),
      seg: document.getElementById('segProgress'),
      thumb: document.getElementById('segThumb'),
      cur: document.getElementById('curTime'),
      dur: document.getElementById('durTime'),
      state: document.getElementById('heroState'),
      title: document.getElementById('heroTitle'),
      cover: document.getElementById('heroCover'),
      mini: document.getElementById('miniPlayer'),
      miniTitle: document.getElementById('miniTitle'),
      miniSub: document.getElementById('miniSub'),
      miniBar: document.getElementById('miniBar'),
      miniCover: document.getElementById('miniCover'),
      miniEq: document.getElementById('miniEq'),
    } : {};
    this.briefing = null;
    this.chapters = [];
    this.segments = [];
    this.current = null;
    this.speed = store.get('rate', 1);
    this.bind();
  }

  get audio() {
    return this.activeAudio;
  }

  bind() {
    const { el } = this;
    if (!el?.play) return;
    el.play.addEventListener('click', () => this.toggle());
    document.getElementById('miniPlay')?.addEventListener('click', () => this.toggle());
    el.prev.addEventListener('click', () => this.prevChapter());
    el.next.addEventListener('click', () => this.nextChapter());
    document.getElementById('miniNext')?.addEventListener('click', () => this.nextChapter());
    document.getElementById('miniPrev')?.addEventListener('click', () => this.prevChapter());
    document.getElementById('back15')?.addEventListener('click', () => this.skip(-15));
    document.getElementById('fwd30')?.addEventListener('click', () => this.skip(30));
    document.getElementById('miniBack')?.addEventListener('click', () => this.skip(-15));

    // Interactive scrubber on floating mini player
    const miniBar = document.getElementById('miniBarWrap') || document.querySelector('.mini-bar');
    if (miniBar) {
      miniBar.addEventListener('click', (e) => {
        e.stopPropagation();
        const r = miniBar.getBoundingClientRect();
        const frac = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
        this.seekTo(frac * (this.total || 0));
      });
    }

    // Big Picture tap to play/pause in story reader
    document.getElementById('readerImagePlayBtn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggle();
    });
    document.getElementById('readerImageWrap')?.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      this.toggle();
    });

    const readerHeroImg = document.getElementById('readerHeroImage');
    if (readerHeroImg) {
      readerHeroImg.addEventListener('error', () => {
        readerHeroImg.src = '/icons/icon-512.png';
      });
    }

    // Clean Player Controls from Mock
    document.getElementById('cleanPlayBtn')?.addEventListener('click', () => this.toggle());
    document.getElementById('cleanPrevBtn')?.addEventListener('click', () => this.prevChapter());
    document.getElementById('cleanNextBtn')?.addEventListener('click', () => this.nextChapter());
    document.getElementById('playerCoverWrap')?.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      this.toggle();
    });

    const cleanCoverImg = document.getElementById('playerCoverImg');
    if (cleanCoverImg) {
      cleanCoverImg.addEventListener('error', () => {
        cleanCoverImg.classList.add('hidden');
        document.getElementById('playerCoverFallback')?.classList.remove('hidden');
      });
      cleanCoverImg.addEventListener('load', () => {
        cleanCoverImg.classList.remove('hidden');
        document.getElementById('playerCoverFallback')?.classList.add('hidden');
      });
    }

    // 40-bar acoustic waveform scrubber
    this.setupCleanWaveform();

    // Speed pills
    this.renderSpeedPills();

    // Tap or drag the segmented bar to seek.
    const seekToEvent = (e) => {
      const r = el.seg.getBoundingClientRect();
      const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      this.seekTo(f * (this.total || 0));
      el.seg.setAttribute('aria-valuenow', String(Math.round(f * 100)));
    };
    let dragging = false;
    el.seg.addEventListener('pointerdown', (e) => { dragging = true; el.seg.setPointerCapture(e.pointerId); seekToEvent(e); });
    el.seg.addEventListener('pointermove', (e) => { if (dragging) seekToEvent(e); });
    el.seg.addEventListener('pointerup', () => { dragging = false; });
    el.seg.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight') this.skip(10);
      else if (e.key === 'ArrowLeft') this.skip(-10);
      else return;
      e.preventDefault();
    });

    // Dual audio elements for seamless background baton pass
    this.setupAudioElement(this.audioA);
    this.setupAudioElement(this.audioB);

    // Keep screen awake while playing in foreground
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && this.isPlaying) {
          this.requestWakeLock();
        }
      });
    }

    // A cover that fails to load hides itself instead of showing a broken icon.
    el.cover?.addEventListener('error', () => el.cover.classList.add('hidden'));
    el.miniCover?.addEventListener('error', () => { el.miniCover.classList.add('hidden'); el.miniEq.classList.remove('hidden'); });

    // Show the floating mini player once the hero scrolls away.
    if (this.hero && typeof IntersectionObserver !== 'undefined') {
      new IntersectionObserver(([entry]) => {
        this.heroInView = entry.isIntersecting;
        this.showMini();
      }, { threshold: 0.05 }).observe(this.hero);
    }

    if (typeof navigator !== 'undefined' && 'mediaSession' in navigator) {
      const ms = navigator.mediaSession;
      ms.setActionHandler('play', () => { if (!this.isPlaying) this.toggle(); });
      ms.setActionHandler('pause', () => { if (this.isPlaying) this.toggle(); });
      ms.setActionHandler('previoustrack', () => this.prevChapter());
      ms.setActionHandler('nexttrack', () => this.nextChapter());
      try { ms.setActionHandler('seekto', (d) => { this.seekTo(d.seekTime); }); } catch { /* unsupported */ }
      try { ms.setActionHandler('seekbackward', (d) => { this.skip(-(d.seekOffset || 15)); }); } catch { /* unsupported */ }
      try { ms.setActionHandler('seekforward', (d) => { this.skip(d.seekOffset || 30); }); } catch { /* unsupported */ }
    }
  }

  setupAudioElement(audioEl) {
    if (!audioEl) return;
    audioEl.addEventListener('timeupdate', () => {
      if (audioEl === this.activeAudio) {
        this.tick();
        this.checkHandoff();
      }
    });
    audioEl.addEventListener('loadedmetadata', () => {
      if (audioEl === this.activeAudio) {
        audioEl.playbackRate = this.speed;
        this.tick();
      }
    });
    audioEl.addEventListener('play', () => {
      if (audioEl === this.activeAudio) {
        this.setPlaying(true);
        this.preloadNext();
      }
    });
    audioEl.addEventListener('pause', () => {
      if (audioEl === this.activeAudio) {
        if (this.handingOff || this.isTransitioningClip) return;
        this.setPlaying(false);
      }
    });
    audioEl.addEventListener('ended', () => {
      if (audioEl === this.activeAudio) {
        this.onEnded();
      }
    });
    audioEl.addEventListener('error', (e) => {
      if (audioEl === this.activeAudio) {
        console.warn('[player] audio error:', e);
      }
    });
  }

  ensureKeepAlive() {
    if (!this.silentAnchor) return;
    try {
      this.silentAnchor.volume = 0.001;
      if (this.silentAnchor.paused) {
        this.silentAnchor.play().catch(() => {});
      }
    } catch {}
  }

  pauseKeepAlive() {
    if (!this.silentAnchor) return;
    try {
      this.silentAnchor.pause();
    } catch {}
  }

  primeAudioChannels() {
    if (this.isPrimed) return;
    this.isPrimed = true;
    this.ensureKeepAlive();
    // Prime standby audio channel in this user gesture so iOS/Android won't block background playback
    if (this.standbyAudio && !this.standbyAudio.src) {
      try {
        this.standbyAudio.volume = 0.001;
        this.standbyAudio.src = '/audio/gap.mp3';
        const p = this.standbyAudio.play();
        if (p && typeof p.then === 'function') {
          p.then(() => {
            this.standbyAudio.pause();
            this.standbyAudio.volume = 1.0;
            this.standbyAudio.removeAttribute('src');
            delete this.standbyAudio.dataset.clip;
          }).catch(() => {});
        }
      } catch {}
    }
  }

  async requestWakeLock() {
    if (typeof navigator !== 'undefined' && 'wakeLock' in navigator && !this.wakeLock) {
      try {
        this.wakeLock = await navigator.wakeLock.request('screen');
        this.wakeLock.addEventListener('release', () => {
          this.wakeLock = null;
        });
      } catch { /* unsupported or battery saver */ }
    }
  }

  async releaseWakeLock() {
    if (this.wakeLock) {
      try {
        await this.wakeLock.release();
      } catch {}
      this.wakeLock = null;
    }
  }

  get isPlaying() {
    return Boolean(this.activeAudio && !this.activeAudio.paused && !this.activeAudio.ended);
  }

  /**
   * The floating player is docked above the toolbar whenever a briefing is loaded.
   */
  showMini() {
    const show = !!this.briefing;
    this.el.mini?.classList.toggle('show', show);
    this.el.mini?.setAttribute('aria-hidden', show ? 'false' : 'true');
  }

  /** Seconds into the whole briefing (not the current clip). */
  get position() {
    if (!this.clips) return (this.activeAudio && this.activeAudio.currentTime) || 0;
    return (this.clips[this.index]?.start || 0) + ((this.activeAudio && this.activeAudio.currentTime) || 0);
  }

  /** Total briefing length. */
  get total() {
    if (!this.clips) return (this.activeAudio && this.activeAudio.duration) || this.briefing?.duration || 0;
    return this.clips.length ? this.clips[this.clips.length - 1].end : 0;
  }

  clipIndexAt(t) {
    let found = 0;
    for (let i = 0; i < this.clips.length; i += 1) { if (t >= this.clips[i].start - 0.02) found = i; }
    return found;
  }

  /** Make clip `i` active, optionally seeking within it, and pre-buffer the next one. */
  loadClip(i, { seek = 0, autoplay = null } = {}) {
    const play = autoplay === null ? this.isPlaying : autoplay;
    const clip = this.clips[i];
    if (!clip) return;
    this.index = i;
    this.handingOff = false;
    const el = this.activeAudio;
    if (!el) return;
    if (el.dataset.clip !== String(i)) {
      el.dataset.clip = String(i);
      el.src = clip.url;
    }
    const applySeek = () => { try { el.currentTime = seek; } catch { /* not seekable yet */ } };
    if (el.readyState >= 1) applySeek();
    else el.addEventListener('loadedmetadata', applySeek, { once: true });
    el.playbackRate = this.speed;
    if (play) {
      this.primeAudioChannels();
      el.play().catch(() => {});
    }
    this.preloadNext();
  }

  /** Buffer the following clip into the standby audio element and verify preload readiness. */
  preloadNext() {
    if (!this.clips || !this.isPlaying) return;
    const nextIdx = this.index + 1;
    const next = this.clips[nextIdx];
    if (!next || !next.url) {
      this.preloadReady = false;
      return;
    }
    const standby = this.standbyAudio;
    if (!standby) return;

    if (standby.dataset.clip !== String(nextIdx)) {
      this.preloadReady = false;
      standby.dataset.clip = String(nextIdx);
      standby.preload = 'auto';
      standby.src = next.url;
      standby.playbackRate = this.speed;

      // Keep a check on pre load
      const markReady = () => {
        if (standby.dataset.clip === String(nextIdx)) {
          this.preloadReady = true;
        }
        standby.removeEventListener('canplay', markReady);
        standby.removeEventListener('canplaythrough', markReady);
      };
      standby.addEventListener('canplay', markReady);
      standby.addEventListener('canplaythrough', markReady);
      standby.load();
    } else if (standby.readyState >= 2) {
      this.preloadReady = true;
    }
  }

  checkHandoff() {
    if (this.handingOff || !this.clips || this.index + 1 >= this.clips.length) return;
    const cur = this.activeAudio;
    if (!cur || !cur.duration || isNaN(cur.duration)) return;
    const remaining = cur.duration - cur.currentTime;
    // Seamless baton pass ~0.35s before current clip ends while outgoing audio still plays
    if (remaining <= 0.35 && remaining >= 0.0) {
      const nextIdx = this.index + 1;
      const standby = this.standbyAudio;
      // Preload check requirement
      if (standby && standby.dataset.clip === String(nextIdx) && (this.preloadReady || standby.readyState >= 2)) {
        this.handOffToNextClip();
      }
    }
  }

  handOffToNextClip() {
    if (this.handingOff || !this.clips || this.index + 1 >= this.clips.length) return;
    const nextIdx = this.index + 1;
    const nextClip = this.clips[nextIdx];
    if (!nextClip) return;

    this.handingOff = true;
    const outgoing = this.activeAudio;
    const incoming = this.standbyAudio;

    if (incoming.dataset.clip !== String(nextIdx)) {
      incoming.dataset.clip = String(nextIdx);
      incoming.src = nextClip.url;
    }
    incoming.playbackRate = this.speed;

    const finalizeHandoff = () => {
      this.index = nextIdx;
      this.activeAudio = incoming;
      this.standbyAudio = outgoing;
      this.handingOff = false;
      this.preloadReady = false;

      try {
        outgoing.pause();
        outgoing.removeAttribute('src');
        delete outgoing.dataset.clip;
      } catch {}

      this.preloadNext();
      this.tick();
      this.syncPositionState();
    };

    const p = incoming.play();
    if (p && typeof p.then === 'function') {
      p.then(() => finalizeHandoff()).catch((err) => {
        console.warn('[player] baton pass play error:', err);
        this.handingOff = false;
      });
    } else {
      finalizeHandoff();
    }
  }

  /** A clip finished: transition seamlessly on standby audio or fallback to active audio. */
  onEnded() {
    if (this.clips && this.index + 1 < this.clips.length) {
      if (this.handingOff) return;
      const nextIdx = this.index + 1;
      const standby = this.standbyAudio;
      if (standby && standby.dataset.clip === String(nextIdx) && (this.preloadReady || standby.readyState >= 2)) {
        this.handOffToNextClip();
        return;
      }
      this.isTransitioningClip = true;
      this.index += 1;
      const clip = this.clips[this.index];
      this.activeAudio.dataset.clip = String(this.index);
      this.activeAudio.src = clip.url;
      this.activeAudio.playbackRate = this.speed;
      const p = this.activeAudio.play();
      if (p && typeof p.catch === 'function') {
        p.catch((err) => {
          this.isTransitioningClip = false;
          console.warn('[player] clip transition error:', err);
        });
      }
      const onPlaying = () => {
        this.isTransitioningClip = false;
        this.activeAudio.removeEventListener('playing', onPlaying);
      };
      this.activeAudio.addEventListener('playing', onPlaying, { once: true });
      setTimeout(() => { this.isTransitioningClip = false; }, 3000);
      this.preloadNext();
      this.tick();
      return;
    }
    this.setPlaying(false);
    const posKey = posKeyFor(this.briefing);
    store.set(posKey, 0);
    this.el.state.textContent = 'Finished';
    this.el.title.textContent = "That's today's briefing. Have a great day!";
  }

  load(briefing) {
    if (!briefing) return;
    const isSameBriefing = Boolean(
      this.briefing &&
      this.briefing.date === briefing.date &&
      this.briefing.mode === briefing.mode &&
      this.briefing.edition === briefing.edition
    );
    const curPos = this.position;

    this.briefing = briefing;
    this.chapters = (briefing.chapters || []).filter((c) => c.kind !== 'section');
    this.clips = briefing.clips && briefing.clips.length ? briefing.clips : null;

    if (isSameBriefing && this.clips && this.clips.length) {
      // Re-align with current timeline position without tearing down playback or restarting at clip 0
      this.index = this.clipIndexAt(curPos);
      this.buildSegments();
      this.tick();
      return;
    }

    this.current = null;
    this.index = 0;
    this.handingOff = false;
    this.preloadReady = false;

    if (this.audioA) {
      this.audioA.pause();
      delete this.audioA.dataset.clip;
      this.audioA.removeAttribute('src');
    }
    if (this.audioB) {
      this.audioB.pause();
      delete this.audioB.dataset.clip;
      this.audioB.removeAttribute('src');
    }
    this.activeAudio = this.audioA;
    this.standbyAudio = this.audioB;

    this.isTransitioningClip = false;
    // In Rapid Fire mode, default to 1.1x speed; in Full mode, restore listener's standard speed.
    if (briefing.mode === 'rapid') {
      this.speed = 1.1;
    } else {
      this.speed = store.get('rate', 1.0);
    }
    if (this.audioA) this.audioA.playbackRate = this.speed;
    if (this.audioB) this.audioB.playbackRate = this.speed;
    this.renderSpeedPills();
    this.syncSpeedPills();

    if (this.clips) this.loadClip(0);
    else if (this.activeAudio) this.activeAudio.src = briefing.audio_url;
    this.buildSegments();
    const posKey = posKeyFor(briefing);
    const saved = store.get(posKey, 0);
    if (saved > 5 && (!briefing.duration || saved < briefing.duration - 5)) this.seekTo(saved);
    this.tick();
  }

  buildSegments() {
    const b = this.briefing;
    const total = Math.max(1, b.duration || 1);
    const ends = this.chapters.map((c, i) => (i + 1 < this.chapters.length ? this.chapters[i + 1].start : b.duration));
    this.segments = this.chapters.map((c, i) => ({ chapter: c, start: c.start, end: ends[i] }));
    const seg = this.el.seg;
    seg.querySelectorAll('.seg').forEach((n) => n.remove());
    for (const s of this.segments) {
      const d = h('div', { class: 'seg', style: `flex-grow:${Math.max(1, s.end - s.start)}` }, h('i'));
      seg.insertBefore(d, this.el.thumb);
    }
  }

  storyFor(chapter) {
    return this.briefing?.stories?.find((s) => s.id === chapter?.id);
  }

  sectionTitle(chapter) {
    const story = this.storyFor(chapter);
    return this.briefing?.sections?.find((s) => s.key === story?.section)?.title || '';
  }

  currentChapter(t = this.position) {
    let found = null;
    for (const c of this.chapters) { if (t >= c.start - 0.05) found = c; }
    return found;
  }

  toggle() {
    if (!this.briefing) return;
    if (this.isPlaying) {
      this.activeAudio.pause();
    } else {
      this.primeAudioChannels();
      window.trackEvent?.('play_briefing', {
        mode: this.briefing.mode || 'podcast',
        title: this.briefing.title,
      });
      if (this.clips && this.clips.length) {
        const targetIdx = this.clipIndexAt(this.position);
        if (targetIdx !== this.index || this.activeAudio.dataset.clip !== String(targetIdx) || !this.activeAudio.src) {
          const seek = Math.max(0, this.position - (this.clips[targetIdx]?.start || 0));
          this.loadClip(targetIdx, { seek, autoplay: true });
          return;
        }
      }
      const p = this.activeAudio.play();
      if (p && typeof p.catch === 'function') {
        p.catch((err) => {
          console.warn('[player] direct play rejected, reloading active clip:', err);
          if (this.clips && this.clips.length) {
            const targetIdx = this.clipIndexAt(this.position);
            const seek = Math.max(0, this.position - (this.clips[targetIdx]?.start || 0));
            this.loadClip(targetIdx, { seek, autoplay: true });
          }
        });
      }
    }
  }

  skip(sec) {
    if (!this.briefing) return;
    this.seekTo(this.position + sec);
  }

  playChapter(id) {
    const ch = this.chapters.find((c) => c.id === id);
    if (!ch) return;
    this.primeAudioChannels();
    window.trackEvent?.('play_story', {
      story_id: id,
      title: ch.title,
      section: ch.section,
    });
    this.seekTo(ch.start);
    this.activeAudio.play().catch(() => {});
  }

  seekTo(seconds) {
    if (!this.briefing) return;
    const limit = this.total || this.briefing.duration || 0;
    const t = Math.max(0, Math.min(seconds, limit));
    if (this.clips) {
      const i = this.clipIndexAt(t);
      if (i !== this.index) {
        this.loadClip(i, { seek: t - this.clips[i].start });
      } else {
        const local = t - this.clips[i].start;
        if (this.audio.readyState >= 1) this.audio.currentTime = local;
        else this.audio.addEventListener('loadedmetadata', () => { this.audio.currentTime = local; }, { once: true });
        this.preloadNext();
      }
    } else if (this.audio.readyState >= 1) {
      this.audio.currentTime = t;
    } else {
      this.audio.addEventListener('loadedmetadata', () => { this.audio.currentTime = t; }, { once: true });
    }
    this.tick();
  }

  nextChapter() {
    const ch = this.currentChapter();
    const i = this.chapters.indexOf(ch);
    if (i >= 0 && i < this.chapters.length - 1) this.playChapter(this.chapters[i + 1].id);
  }

  prevChapter() {
    const ch = this.currentChapter();
    const i = this.chapters.indexOf(ch);
    if (ch && this.position - ch.start > 3) this.playChapter(ch.id);
    else if (i > 0) this.playChapter(this.chapters[i - 1].id);
  }

  setupCleanWaveform() {
    const barsWrap = document.getElementById('cleanWaveBars');
    if (!barsWrap) return;
    const heights = [12, 20, 28, 16, 32, 24, 36, 18, 30, 36, 22, 32, 14, 34, 26, 36, 20, 28, 16, 32, 24, 36, 12, 30, 22, 34, 18, 36, 26, 14, 32, 20, 36, 28, 16, 32, 24, 18, 30, 22];
    barsWrap.replaceChildren(...heights.map((h, i) => {
      const s = document.createElement('span');
      s.className = 'clean-wave-bar';
      s.style.height = `${h}px`;
      s.dataset.idx = String(i);
      return s;
    }));

    const seekFromEvent = (e) => {
      const r = barsWrap.getBoundingClientRect();
      const frac = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
      this.seekTo(frac * (this.total || 0));
      barsWrap.setAttribute('aria-valuenow', String(Math.round(frac * 100)));
    };

    let dragging = false;
    barsWrap.addEventListener('pointerdown', (e) => {
      dragging = true;
      try { barsWrap.setPointerCapture(e.pointerId); } catch {}
      seekFromEvent(e);
    });
    barsWrap.addEventListener('pointermove', (e) => {
      if (dragging) seekFromEvent(e);
    });
    barsWrap.addEventListener('pointerup', (e) => {
      dragging = false;
      try { barsWrap.releasePointerCapture(e.pointerId); } catch {}
    });
    barsWrap.addEventListener('pointercancel', (e) => {
      dragging = false;
      try { barsWrap.releasePointerCapture(e.pointerId); } catch {}
    });
  }

  renderSpeedPills() {
    const box = document.getElementById('speedPills');
    if (!box) return;
    const isRapid = this.briefing?.mode === 'rapid';
    const speeds = isRapid ? [1.0, 1.1, 1.25, 1.5] : [0.8, 1.0, 1.25, 1.5];
    box.replaceChildren(...speeds.map((s) => {
      const b = h('button', {
        type: 'button',
        class: 'seg-opt' + (Math.abs(this.speed - s) < 0.05 ? ' on' : ''),
      }, `${s}x`);
      b.addEventListener('click', () => this.setRate(s));
      return b;
    }));
  }

  syncSpeedPills() {
    document.querySelectorAll('#speedPills .seg-opt').forEach((btn) => {
      const val = parseFloat(btn.textContent);
      btn.classList.toggle('on', Math.abs(this.speed - val) < 0.05);
    });
  }

  setRate(rate) {
    this.speed = rate;
    if (this.audioA) this.audioA.playbackRate = rate;
    if (this.audioB) this.audioB.playbackRate = rate;
    if (this.briefing?.mode !== 'rapid') {
      store.set('rate', rate);
    }
    this.syncSpeedPills();
    this.syncPositionState();
  }

  setPlaying(on) {
    if (on) {
      this.ensureKeepAlive();
      this.requestWakeLock();
    } else {
      this.pauseKeepAlive();
      this.releaseWakeLock();
    }
    document.body.classList.toggle('playing', on);
    if (this.hero) this.hero.classList.toggle('playing-now', on);
    if (this.el?.play) this.el.play.setAttribute('aria-label', on ? 'Pause briefing' : 'Play briefing');
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = on ? 'playing' : 'paused';
    const liveStatus = document.getElementById('liveStatus');
    if (liveStatus) liveStatus.textContent = on ? 'Playing' : 'Paused';
    if (window.HarkNative) {
      try {
        window.HarkNative.setKeepScreenOn(on);
        const story = this.briefing?.stories?.[this.storyIndex];
        const ch = this.currentChapter;
        const title = ch?.title || story?.headline || this.briefing?.title || 'Hark Daily';
        const artist = 'Hark Daily \u2022 ' + (this.briefing?.title || 'Briefing');
        window.HarkNative.notifyPlaybackState(on, title, artist);
      } catch {}
    }
    this.dispatchEvent(new CustomEvent('state', { detail: { playing: on } }));
  }

  tick() {
    const { el } = this;
    const b = this.briefing;
    if (!b) return;
    const dur = this.total || b.duration || 0;
    const t = this.position;
    if (t > 0 && Math.round(t) % 5 === 0) {
      const posKey = posKeyFor(b);
      store.set(posKey, t);
      this.syncPositionState();
    }

    // Segments + thumb.
    const segs = el.seg.querySelectorAll('.seg');
    this.segments.forEach((s, i) => {
      const f = s.end > s.start ? Math.min(1, Math.max(0, (t - s.start) / (s.end - s.start))) : 0;
      const fill = segs[i]?.firstChild;
      if (fill) fill.style.width = `${f * 100}%`;
    });
    const frac = dur ? t / dur : 0;
    el.thumb.style.left = `${frac * 100}%`;
    el.seg.setAttribute('aria-valuenow', String(Math.round(frac * 100)));

    // Times: elapsed and remaining.
    if (el.cur) el.cur.textContent = fmtTime(t);
    if (el.dur) el.dur.textContent = `-${fmtTime(Math.max(0, dur - t))}`;
    const cleanCur = document.getElementById('cleanCurTime');
    if (cleanCur) cleanCur.textContent = fmtTime(t);
    const cleanDur = document.getElementById('cleanDurTime');
    if (cleanDur) cleanDur.textContent = `-${fmtTime(Math.max(0, dur - t))}`;

    // Update 40 acoustic waveform bars
    const cleanWaveBars = document.querySelectorAll('#cleanWaveBars .clean-wave-bar');
    if (cleanWaveBars.length) {
      const activeCount = Math.round(frac * cleanWaveBars.length);
      cleanWaveBars.forEach((bar, idx) => {
        bar.classList.toggle('active', idx < activeCount);
      });
    }

    // Hero state + title + cover.
    const ch = this.currentChapter(t);
    const story = this.storyFor(ch);
    const section = this.sectionTitle(ch);
    const started = t >= 0.5;
    el.state.textContent = !started && !this.isPlaying
      ? `Ready · ${b.stories.length} ${b.stories.length === 1 ? 'story' : 'stories'}`
      : (this.isPlaying ? 'Now playing' : 'Paused');
    el.title.textContent = story?.headline || ch?.title || b.title;

    // Hero section label & count
    const heroSection = document.getElementById('heroSection');
    if (heroSection) heroSection.textContent = section ? `· ${section}` : '';
    const heroCount = document.getElementById('heroCount');
    if (heroCount) {
      const idx = story ? b.stories.indexOf(story) + 1 : 0;
      heroCount.textContent = idx ? `Story ${idx} of ${b.stories.length}` : (b.stories?.length ? `${b.stories.length} stories` : '');
    }
    const heroArticle = document.getElementById('heroArticle');
    if (heroArticle) {
      if (story?.url) {
        heroArticle.href = story.url;
        heroArticle.classList.remove('hidden');
      } else {
        heroArticle.classList.add('hidden');
      }
    }
    const heroShare = document.getElementById('heroShare');
    if (heroShare) {
      if (story) {
        heroShare.classList.remove('hidden');
        heroShare.onclick = (e) => {
          e.stopPropagation();
          window.openShareModal?.(story);
        };
      } else {
        heroShare.classList.add('hidden');
      }
    }

    // Sidebar daily progress & live status
    const progVal = document.getElementById('dayProgressVal');
    if (progVal) progVal.textContent = `${fmtTime(t)} / ${fmtTime(dur)}`;
    const progBar = document.getElementById('dayProgressBar');
    if (progBar) progBar.style.width = `${frac * 100}%`;
    const liveStatus = document.getElementById('liveStatus');
    if (liveStatus) liveStatus.textContent = this.isPlaying ? 'Playing' : (t > 0 ? 'Paused' : 'Ready');

    // Synchronized expanded story reader & transcript
    const transBox = document.getElementById('transcript');
    const transText = document.getElementById('transcriptText');
    const transBody = document.getElementById('transcriptBody');

    // Update expanded reader header & footer
    const readerBadge = document.getElementById('readerSectionBadge');
    if (readerBadge) {
      const secKey = story?.section || 'top';
      readerBadge.textContent = (section || story?.section || 'TOP STORIES').toUpperCase();
      readerBadge.className = `badge badge-cat cat-${secKey}`;
    }
    const readerSource = document.getElementById('readerSource');
    if (readerSource) readerSource.textContent = story?.source || 'Daily News';
    const readerCount = document.getElementById('readerStoryCount');
    if (readerCount) {
      const idx = story ? b.stories.indexOf(story) + 1 : 0;
      readerCount.textContent = idx ? `Story ${idx} of ${b.stories.length}` : `${b.stories.length} stories`;
    }
    const readerHeadline = document.getElementById('readerHeadline');
    if (readerHeadline) {
      readerHeadline.textContent = story?.headline || ch?.title || b.title;
    }
    const readerArticleLink = document.getElementById('readerArticleLink');
    if (readerArticleLink) {
      if (story?.url) {
        readerArticleLink.href = story.url;
        const srcName = story?.source ? story.source.split('·')[0].trim() : 'original source';
        const span = readerArticleLink.querySelector('span');
        if (span) span.textContent = `Full story on ${srcName}`;
        readerArticleLink.classList.remove('hidden');
      } else {
        readerArticleLink.classList.add('hidden');
      }
    }
    const readerShareBtn = document.getElementById('readerShareBtn');
    if (readerShareBtn && story) {
      readerShareBtn.onclick = (e) => {
        e.stopPropagation();
        window.openShareModal?.(story);
      };
    }
    const readerQueueLabel = document.getElementById('readerQueueLabel');
    if (readerQueueLabel) {
      readerQueueLabel.textContent = `All ${b.stories.length} stories`;
    }

    let activeSpeaker = null;
    if (transBox && transText && transBody) {
      const text = story?.script || story?.summary || story?.headline || ch?.text || ch?.title || '';
      if (text) {
        transBox.classList.remove('hidden');
        const currentId = story?.id || ch?.id || '';
        if (transText.dataset.storyId !== currentId) {
          transText.dataset.storyId = currentId;
          transBody.scrollTop = 0;

          const dialogueTurns = parseDialogueTurns(text);
          if (dialogueTurns && dialogueTurns.length) {
            const weights = dialogueTurns.map((turn) => Math.max(1, turn.text.length));
            const totalWeight = weights.reduce((a, b) => a + b, 0);
            let running = 0;
            const cumFractions = weights.map((w) => {
              const start = running / totalWeight;
              running += w;
              return { start, end: running / totalWeight };
            });

            transText._storyData = { dialogueTurns, cumFractions };
            transText.replaceChildren(...dialogueTurns.map((turn, idx) => {
              const spkSlug = (turn.speaker || 'host').toLowerCase().replace(/[^a-z0-9]+/g, '-');
              return h('span', {
                class: `w clean-dialogue-turn turn-${spkSlug}`,
                role: 'button',
                tabindex: '0',
                title: `Jump to ${turn.speaker}'s line`,
                dataset: { idx: String(idx), speaker: turn.speaker },
                onclick: (e) => {
                  e.stopPropagation();
                  const chDur = Math.max(1, (ch?.end || dur) - (ch?.start || 0));
                  const targetSec = (ch?.start || 0) + (cumFractions[idx].start * chDur);
                  this.seekTo(targetSec);
                  if (!this.isPlaying) {
                    this.primeAudioChannels();
                    this.audio.play().catch(() => {});
                  }
                },
              },
              h('span', { class: `clean-turn-speaker speaker-${spkSlug}` }, turn.speaker),
              h('span', { class: 'clean-turn-text' }, turn.text + ' '));
            }));
          } else {
            const sentences = splitSentences(text);
            const weights = sentences.map((s) => Math.max(1, s.length));
            const totalWeight = weights.reduce((a, b) => a + b, 0);
            let running = 0;
            const cumFractions = weights.map((w) => {
              const start = running / totalWeight;
              running += w;
              return { start, end: running / totalWeight };
            });

            transText._storyData = { sentences, cumFractions };
            transText.replaceChildren(...sentences.map((s, idx) => h('span', {
              class: 'w',
              role: 'button',
              tabindex: '0',
              title: 'Jump to this sentence',
              dataset: { idx: String(idx) },
              onclick: (e) => {
                e.stopPropagation();
                const chDur = Math.max(1, (ch?.end || dur) - (ch?.start || 0));
                const targetSec = (ch?.start || 0) + (cumFractions[idx].start * chDur);
                this.seekTo(targetSec);
                if (!this.isPlaying) {
                  this.primeAudioChannels();
                  this.audio.play().catch(() => {});
                }
              },
            }, s + ' ')));
          }

          if (!transBody._scrollListenersAttached) {
            transBody._scrollListenersAttached = true;
            const markUserScroll = () => {
              transBody._userScrollUntil = Date.now() + 2800;
            };
            transBody.addEventListener('touchstart', markUserScroll, { passive: true });
            transBody.addEventListener('wheel', markUserScroll, { passive: true });
            transBody.addEventListener('mousedown', markUserScroll, { passive: true });
          }
        }

        const chDur = Math.max(1, (ch?.end || dur) - (ch?.start || 0));
        const chProgress = Math.min(1, Math.max(0, (t - (ch?.start || 0)) / chDur));
        const spans = transText.querySelectorAll('.w');
        const cumFractions = transText._storyData?.cumFractions;
        const dialogueTurns = transText._storyData?.dialogueTurns;

        let activeIdx = 0;
        if (cumFractions && cumFractions.length === spans.length) {
          for (let i = 0; i < cumFractions.length; i++) {
            if (chProgress >= cumFractions[i].start) {
              activeIdx = i;
            }
          }
        } else if (spans.length) {
          activeIdx = Math.min(spans.length - 1, Math.floor(chProgress * spans.length));
        }

        if (dialogueTurns && dialogueTurns[activeIdx]) {
          activeSpeaker = dialogueTurns[activeIdx].speaker;
        }

        spans.forEach((sp, idx) => {
          sp.classList.toggle('done', idx < activeIdx);
          sp.classList.toggle('now', idx === activeIdx);
        });

        // Auto-scroll transcript container smoothly so the active line stays in view
        const isUserScrolling = transBody._userScrollUntil && Date.now() < transBody._userScrollUntil;
        if (!isUserScrolling && spans.length > 0) {
          const activeSpan = spans[activeIdx];
          if (activeSpan) {
            if (activeIdx === spans.length - 1 || chProgress >= 0.95) {
              if (transBody.scrollTop < transBody.scrollHeight - transBody.clientHeight - 4) {
                transBody.scrollTo({ top: transBody.scrollHeight, behavior: 'smooth' });
              }
            } else {
              const spanRect = activeSpan.getBoundingClientRect();
              const bodyRect = transBody.getBoundingClientRect();
              const relativeTop = spanRect.top - bodyRect.top + transBody.scrollTop;
              const targetScroll = Math.max(0, relativeTop - Math.floor(bodyRect.height * 0.28));
              if (Math.abs(transBody.scrollTop - targetScroll) > 8) {
                transBody.scrollTo({ top: targetScroll, behavior: 'smooth' });
              }
            }
          }
        }
      }
    }

    // Cover image determination:
    // During intro chat, host banter, or outro sign-off, show the official podcast logo.
    // When a story is playing, show the story's editorial image.
    const isIntroOrBanter = !story && ch && (
      (typeof ch.id === 'string' && (
        ch.id.startsWith('pod_open') ||
        ch.id.startsWith('pod_tease') ||
        ch.id.startsWith('greeting') ||
        ch.id.startsWith('pod_close') ||
        ch.id === 'outro'
      )) || ch.kind === 'note'
    );
    let img = null;
    if (story?.image) {
      img = story.image;
    } else if (isIntroOrBanter) {
      img = '/icons/icon-512.png';
    } else {
      const upNext = this.chapters.find((c) => c.kind === 'story' && c.start >= t - 0.01);
      img = (story || this.storyFor(upNext))?.image || '/icons/icon-512.png';
    }
    if (img && el.cover && el.cover.dataset.src !== img) { el.cover.dataset.src = img; el.cover.src = img; el.cover.classList.remove('hidden'); }
    else if (!img && el.cover) el.cover.classList.add('hidden');

    // Update Big Picture in the story reader
    const readerImg = document.getElementById('readerHeroImage');
    if (readerImg) {
      if (img && readerImg.dataset.src !== img) {
        readerImg.dataset.src = img;
        readerImg.src = img;
      }
    }
    const readerBadgeText = document.getElementById('readerImageBadgeText');
    if (readerBadgeText) {
      if (isIntroOrBanter) {
        readerBadgeText.textContent = this.briefing?.mode === 'podcast' ? 'Voiced by AI Duo · Matthew & Kelly' : 'Daily Brief Intro';
      } else if (story) {
        const idx = b.stories.indexOf(story) + 1;
        readerBadgeText.textContent = idx ? `Now Voicing · Story ${idx} of ${b.stories.length}` : 'Now Voicing';
      } else {
        readerBadgeText.textContent = 'Voiced on Hark Daily';
      }
    }

    // Update Clean Player cover image (showcasing article image in Now Voicing section)
    const cleanCoverImg = document.getElementById('playerCoverImg');
    const cleanCoverFallback = document.getElementById('playerCoverFallback');
    const ambientBackdrop = document.getElementById('ambientStoryBackdrop');
    if (img && cleanCoverImg) {
      if (cleanCoverImg.dataset.src !== img) {
        cleanCoverImg.dataset.src = img;
        cleanCoverImg.src = img;
      }
      cleanCoverImg.classList.remove('hidden');
      cleanCoverFallback?.classList.add('hidden');
      if (ambientBackdrop && ambientBackdrop.dataset.bg !== img) {
        ambientBackdrop.dataset.bg = img;
        ambientBackdrop.style.backgroundImage = `url("${img}")`;
        ambientBackdrop.classList.add('has-image');
      }
    } else if (cleanCoverImg) {
      cleanCoverImg.classList.add('hidden');
      cleanCoverFallback?.classList.remove('hidden');
      if (ambientBackdrop && ambientBackdrop.dataset.bg) {
        ambientBackdrop.dataset.bg = '';
        ambientBackdrop.style.backgroundImage = '';
        ambientBackdrop.classList.remove('has-image');
      }
    }

    const cleanNowVoicing = document.getElementById('playerCoverBadgeText');
    if (cleanNowVoicing) {
      if (isIntroOrBanter) {
        cleanNowVoicing.textContent = 'AI Duo · Matthew & Kelly';
      } else if (activeSpeaker) {
        cleanNowVoicing.textContent = `AI Duo · Matthew & Kelly · ${activeSpeaker}`;
      } else if (this.briefing?.mode === 'podcast') {
        cleanNowVoicing.textContent = 'AI Duo · Matthew & Kelly';
      } else {
        cleanNowVoicing.textContent = 'Now voicing';
      }
    }

    // Clean Player Story Metadata & Actions
    const cleanCat = document.getElementById('cleanCatBadge');
    if (cleanCat) {
      cleanCat.textContent = (section || story?.section || 'TOP STORIES').toUpperCase();
    }
    const cleanSrc = document.getElementById('cleanSourceTitle');
    if (cleanSrc) {
      cleanSrc.textContent = story?.source ? story.source.split('·')[0].trim() : 'Daily News';
    }
    const cleanCounter = document.getElementById('cleanStoryCounter');
    if (cleanCounter) {
      const idx = story ? b.stories.indexOf(story) + 1 : 0;
      cleanCounter.textContent = idx ? `${idx} / ${b.stories.length}` : (b.stories?.length ? `1 / ${b.stories.length}` : '1 / 1');
    }
    const cleanHeadline = document.getElementById('cleanStoryHeadline');
    if (cleanHeadline) {
      cleanHeadline.textContent = story?.headline || ch?.title || b.title;
    }

    const cleanShare = document.getElementById('cleanShareBtn');
    if (cleanShare && story) {
      cleanShare.onclick = (e) => {
        e.stopPropagation();
        window.openShareModal?.(story);
      };
    }

    const cleanSourceLink = document.getElementById('cleanSourceLink');
    const cleanSourceLinkName = document.getElementById('cleanSourceLinkName');
    if (cleanSourceLink) {
      if (story?.url) {
        cleanSourceLink.href = story.url;
        const srcName = story?.source ? story.source.split('·')[0].trim() : 'original source';
        if (cleanSourceLinkName) cleanSourceLinkName.textContent = `Read on ${srcName}`;
        cleanSourceLink.classList.remove('hidden');
      } else {
        cleanSourceLink.classList.add('hidden');
      }
    }

    // Floating Mini player docked above toolbar
    el.miniTitle.textContent = story?.headline || ch?.title || b.title;
    el.miniSub.textContent = [section, `${fmtTime(t)} / ${fmtTime(dur)}`].filter(Boolean).join(' · ');
    el.miniBar.style.width = `${frac * 100}%`;
    if (img && el.miniCover.dataset.src !== img) { el.miniCover.dataset.src = img; el.miniCover.src = img; el.miniCover.classList.remove('hidden'); el.miniEq.classList.add('hidden'); }
    else if (!img) { el.miniCover.classList.add('hidden'); el.miniEq.classList.remove('hidden'); }
    this.showMini();

    if (ch && ch.id !== this.current && (t > 0 || this.isPlaying)) {
      this.current = ch.id;
      this.updateMediaSession(ch, story);
      this.dispatchEvent(new CustomEvent('chapter', { detail: ch }));
    }
  }

  updateMediaSession(ch, story) {
    if (window.HarkNative && this.isPlaying) {
      try {
        const title = ch?.title || story?.headline || this.briefing?.title || 'Hark Daily';
        const artist = 'Hark Daily \u2022 ' + (this.briefing?.title || 'Briefing');
        window.HarkNative.notifyPlaybackState(true, title, artist);
      } catch {}
    }
    if (!('mediaSession' in navigator)) return;
    const art = story?.image ? [{ src: story.image, sizes: '512x512' }] : [];
    navigator.mediaSession.metadata = new MediaMetadata({
      title: ch?.title || story?.headline || this.briefing?.title || 'Hark Daily',
      artist: 'Hark Daily',
      album: this.briefing?.title || 'Daily Briefing',
      artwork: [...art, { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' }],
    });
    this.syncPositionState();
  }

  syncPositionState() {
    if (!('mediaSession' in navigator) || typeof navigator.mediaSession.setPositionState !== 'function') return;
    try {
      const dur = this.total || this.briefing?.duration || 1;
      const pos = Math.min(dur, Math.max(0, this.position));
      navigator.mediaSession.setPositionState({
        duration: dur,
        playbackRate: this.speed,
        position: pos,
      });
    } catch { /* unsupported or rapid seek mismatch */ }
  }
}
