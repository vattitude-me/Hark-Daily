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

/** High-quality default SVG artwork per category when article images are missing or blocked. */
export function getDefaultCover(section = '') {
  const s = String(section || '').toLowerCase();
  if (s.includes('sport') || s.includes('cricket')) return '/icons/covers/sports.svg';
  if (s.includes('tech')) return '/icons/covers/tech.svg';
  if (s.includes('market')) return '/icons/covers/markets.svg';
  if (s.includes('politi')) return '/icons/covers/politics.svg';
  if (s.includes('entertain')) return '/icons/covers/entertainment.svg';
  if (s.includes('ai')) return '/icons/covers/ai.svg';
  if (s.includes('scien')) return '/icons/covers/science.svg';
  return '/icons/covers/default.svg';
}

export class Player extends EventTarget {
  constructor({ audio, preloader } = {}) {
    super();
    this.failedImages = new Set();
    // Authoritative single audio element for playback to ensure stable mobile AudioFocus,
    // lock-screen MediaSession ownership, and continuous background play.
    // Secondary element audioB is used strictly as a silent cache preloader.
    const hasDoc = typeof document !== 'undefined';
    this.audio = audio || (hasDoc && document.getElementById('audio')) || (typeof Audio !== 'undefined' ? new Audio() : null);
    this.preloader = preloader || (hasDoc && document.getElementById('audioB')) || (typeof Audio !== 'undefined' ? new Audio() : null);
    this.isPrimed = false;
    this.wakeLock = null;
    this.isTransitioningClip = false;

    if (this.audio) {
      this.audio.preload = 'auto';
      this.audio.volume = 1.0;
      this.audio.muted = false;
    }
    if (this.preloader) {
      this.preloader.preload = 'auto';
      this.preloader.volume = 0.0;
      this.preloader.muted = true;
    }

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

  get activeAudio() {
    return this.audio;
  }

  get audioA() {
    return this.audio;
  }

  get audioB() {
    return this.preloader;
  }

  get standbyAudio() {
    return this.preloader;
  }

  bind() {
    if (typeof document === 'undefined') return;
    const { el } = this;
    if (!el) return;
    el.play?.addEventListener('click', () => this.toggle());
    document.getElementById('miniPlay')?.addEventListener('click', () => this.toggle());
    el.prev?.addEventListener('click', () => this.prevChapter());
    el.next?.addEventListener('click', () => this.nextChapter());
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
        const failed = readerHeroImg.dataset.src;
        if (failed && !failed.startsWith('/icons/covers/')) {
          this.failedImages.add(failed);
        }
        const currentSec = this.currentStory()?.section || this.currentSection || 'top';
        const fallback = getDefaultCover(currentSec);
        readerHeroImg.dataset.src = fallback;
        readerHeroImg.src = fallback;
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
        const failed = cleanCoverImg.dataset.src || cleanCoverImg.src;
        const fallbackCard = document.getElementById('playerCoverFallback');
        if (failed && !failed.startsWith('/icons/covers/')) {
          this.failedImages.add(failed);
          const currentSec = this.currentStory()?.section || this.currentSection || 'top';
          const fallback = getDefaultCover(currentSec);
          cleanCoverImg.dataset.src = fallback;
          cleanCoverImg.src = fallback;
          cleanCoverImg.classList.remove('hidden');
          fallbackCard?.classList.add('hidden');
          const ambientBackdrop = document.getElementById('ambientStoryBackdrop');
          if (ambientBackdrop && ambientBackdrop.dataset.bg !== fallback) {
            ambientBackdrop.dataset.bg = fallback;
            ambientBackdrop.style.backgroundImage = `url("${fallback}")`;
            ambientBackdrop.classList.add('has-image');
          }
        } else {
          // If the SVG fallback itself failed to load, gracefully hide the broken img and reveal gradient orb
          cleanCoverImg.classList.add('hidden');
          fallbackCard?.classList.remove('hidden');
        }
      });
      cleanCoverImg.addEventListener('load', () => {
        cleanCoverImg.classList.remove('hidden');
        document.getElementById('playerCoverFallback')?.classList.add('hidden');
      });
    }

    const rearCoverImg = document.getElementById('rearCoverImg');
    if (rearCoverImg) {
      rearCoverImg.addEventListener('error', () => {
        const failed = rearCoverImg.dataset.src || rearCoverImg.src;
        if (failed && !failed.startsWith('/icons/covers/')) {
          this.failedImages.add(failed);
          const b = this.briefing;
          const story = this.currentStory();
          const currentStoryIdx = story ? b.stories.indexOf(story) : 0;
          const nextStory = b.stories?.[currentStoryIdx + 1];
          const nextSec = nextStory?.section || 'top';
          const fallback = getDefaultCover(nextSec);
          rearCoverImg.dataset.src = fallback;
          rearCoverImg.src = fallback;
        }
      });
    }

    // 40-bar acoustic waveform scrubber
    this.setupCleanWaveform();

    // 3D Stacked cards gesture swipe navigation
    this.setupCardSwipe();

    // Speed pills
    this.renderSpeedPills();

    // Tap or drag the segmented bar to seek.
    if (el?.seg) {
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
    }

    // Setup authoritative playback audio element
    this.setupAudioElement(this.audio);

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
      this.tick();
    });
    audioEl.addEventListener('loadedmetadata', () => {
      audioEl.playbackRate = this.speed;
      this.tick();
    });
    audioEl.addEventListener('play', () => {
      if (this._transitionSafetyTimer) clearTimeout(this._transitionSafetyTimer);
      this.isTransitioningClip = false;
      this.setPlaying(true);
      this.preloadNext();
    });
    audioEl.addEventListener('playing', () => {
      if (this._transitionSafetyTimer) clearTimeout(this._transitionSafetyTimer);
      this.isTransitioningClip = false;
      this.setPlaying(true);
    });
    audioEl.addEventListener('pause', () => {
      if (this.isTransitioningClip) return;
      this.setPlaying(false);
    });
    audioEl.addEventListener('ended', () => {
      this.onEnded();
    });
    audioEl.addEventListener('error', (e) => {
      console.warn('[player] audio error:', e);
      const clip = this.clips?.[this.index];
      if ((clip?.gap || clip?.banter || clip?.note) && this.clips && this.index + 1 < this.clips.length) {
        console.log('[player] transition audio error, advancing to next clip');
        this.isTransitioningClip = true;
        this.loadClip(this.index + 1, { seek: 0, autoplay: true, forceReload: true });
      }
    });
  }

  primeAudioChannels() {
    if (this.isPrimed) return;
    this.isPrimed = true;
    if (this.audio) {
      this.audio.volume = 1.0;
      this.audio.muted = false;
    }
    if (this.preloader) {
      this.preloader.volume = 0.0;
      this.preloader.muted = true;
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
    return Boolean(this.audio && !this.audio.paused && !this.audio.ended);
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
    if (!this.clips) return (this.audio && this.audio.currentTime) || 0;
    return (this.clips[this.index]?.start || 0) + ((this.audio && this.audio.currentTime) || 0);
  }

  /** Total briefing length. */
  get total() {
    if (!this.clips) return (this.audio && this.audio.duration) || this.briefing?.duration || 0;
    return this.clips.length ? this.clips[this.clips.length - 1].end : 0;
  }

  clipIndexAt(t) {
    let found = 0;
    for (let i = 0; i < this.clips.length; i += 1) { if (t >= this.clips[i].start - 0.02) found = i; }
    return found;
  }

  /** Make clip `i` active, optionally seeking within it, and pre-buffer the next one. */
  loadClip(i, { seek = 0, autoplay = null, forceReload = false } = {}) {
    const play = autoplay === null ? this.isPlaying : autoplay;
    const clip = this.clips?.[i];
    if (!clip) return;
    this.index = i;
    const el = this.audio;
    if (!el) return;

    if (this._transitionSafetyTimer) clearTimeout(this._transitionSafetyTimer);
    if (play) {
      this.isTransitioningClip = true;
      this._transitionSafetyTimer = setTimeout(() => {
        this.isTransitioningClip = false;
      }, 5000);
    } else {
      this.isTransitioningClip = false;
    }

    if (this.preloader && this.preloader.dataset.clip === String(i)) {
      try {
        this.preloader.pause();
        this.preloader.removeAttribute('src');
        delete this.preloader.dataset.clip;
      } catch {}
    }

    const needsLoad = forceReload || el.dataset.clip !== String(i) || !el.src || el.error;
    if (needsLoad) {
      el.dataset.clip = String(i);
      el.src = clip.url;
      try { el.load(); } catch {}
    }
    if (seek > 0) {
      const applySeek = () => { try { el.currentTime = seek; } catch { /* not seekable yet */ } };
      if (el.readyState >= 1) applySeek();
      else el.addEventListener('loadedmetadata', applySeek, { once: true });
    }
    el.playbackRate = this.speed;
    el.volume = 1.0;
    el.muted = false;
    if (play) {
      this.primeAudioChannels();
      const p = el.play();
      if (p && typeof p.then === 'function') {
        p.then(() => {
          if (this._transitionSafetyTimer) clearTimeout(this._transitionSafetyTimer);
          this.isTransitioningClip = false;
        }).catch((err) => {
          if (this._transitionSafetyTimer) clearTimeout(this._transitionSafetyTimer);
          this.isTransitioningClip = false;
          console.warn('[player] loadClip play failed:', err);
          if ((clip?.gap || clip?.banter || clip?.note) && this.clips && this.index + 1 < this.clips.length) {
            console.log('[player] transition audio play failed, advancing to next clip');
            this.isTransitioningClip = true;
            this.loadClip(this.index + 1, { seek: 0, autoplay: true, forceReload: true });
          }
        });
      } else {
        if (this._transitionSafetyTimer) clearTimeout(this._transitionSafetyTimer);
        this.isTransitioningClip = false;
      }
    }
    this.preloadNext();
  }

  /** Pre-buffer the following clip silently into cache using the secondary audio preloader. */
  preloadNext() {
    if (!this.clips || !this.isPlaying) return;
    let nextIdx = this.index + 1;
    while (nextIdx < this.clips.length && this.clips[nextIdx]?.gap) {
      nextIdx++;
    }
    const next = this.clips[nextIdx];
    if (!next || !next.url) return;
    const preloader = this.preloader;
    if (!preloader) return;

    if (preloader.dataset.clip !== String(nextIdx)) {
      preloader.dataset.clip = String(nextIdx);
      preloader.preload = 'auto';
      preloader.src = next.url;
      try { preloader.load(); } catch {}
    }
  }

  /** A clip finished: advance directly to next clip on the authoritative audio channel. */
  onEnded() {
    if (this.clips && this.index + 1 < this.clips.length) {
      this.isTransitioningClip = true;
      const nextIdx = this.index + 1;
      this.loadClip(nextIdx, { seek: 0, autoplay: true, forceReload: true });
      this.tick();
      this.syncPositionState();
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

    if (this.audio) {
      this.audio.pause();
      delete this.audio.dataset.clip;
      this.audio.removeAttribute('src');
    }
    if (this.preloader) {
      this.preloader.pause();
      delete this.preloader.dataset.clip;
      this.preloader.removeAttribute('src');
    }

    this.isTransitioningClip = false;
    // In Rapid Fire mode, default to 1.1x speed; in Full mode, restore listener's standard speed.
    if (briefing.mode === 'rapid') {
      this.speed = 1.1;
    } else {
      this.speed = store.get('rate', 1.0);
    }
    if (this.audio) this.audio.playbackRate = this.speed;
    this.renderSpeedPills();
    this.syncSpeedPills();

    if (this.clips) this.loadClip(0);
    else if (this.audio) this.audio.src = briefing.audio_url;
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
    if (!chapter || !this.briefing?.stories?.length) return null;
    const stories = this.briefing.stories;
    const direct = stories.find((s) => s.id === chapter.id);
    if (direct) return direct;

    // If chapter has an explicit section (e.g. section bridge banter 'pod_bridge_entertainment'),
    // associate it with the first story of that section
    if (chapter.section) {
      const baseSec = chapter.section.replace(/_(us|in|ca)$/, '');
      const secStory = stories.find((s) => s.section === chapter.section || s.section === baseSec || (s.section || '').replace(/_(us|in|ca)$/, '') === baseSec);
      if (secStory) return secStory;
    }

    // Resolve by timeline timestamp: find the story covering or immediately following this chapter
    const t = typeof chapter.start === 'number' ? chapter.start : this.position;
    const active = stories.find((s) => t >= s.start - 0.05 && t < s.end);
    if (active) return active;

    const next = stories.find((s) => s.start >= t - 0.1);
    if (next) return next;

    const prev = [...stories].reverse().find((s) => s.start <= t + 0.1);
    if (prev) return prev;

    return stories[0] || null;
  }

  currentStory(t = this.position) {
    const ch = this.currentChapter(t);
    if (ch) return this.storyFor(ch);
    const stories = this.briefing?.stories;
    if (!stories?.length) return null;
    const active = stories.find((s) => t >= s.start - 0.05 && t < s.end);
    if (active) return active;
    const next = stories.find((s) => s.start >= t - 0.1);
    if (next) return next;
    return stories[stories.length - 1] || null;
  }

  sectionTitle(chapter) {
    const story = this.storyFor(chapter);
    const secKey = chapter?.section || story?.section;
    return this.briefing?.sections?.find((s) => s.key === secKey)?.title || '';
  }

  currentChapter(t = this.position) {
    let found = null;
    for (const c of this.chapters) { if (t >= c.start - 0.05) found = c; }
    return found;
  }

  toggle() {
    if (!this.briefing) return;
    this.isTransitioningClip = false;

    if (this.isPlaying) {
      this.audio.pause();
    } else {
      this.primeAudioChannels();
      if (typeof window !== 'undefined') {
        window.trackEvent?.('play_briefing', {
          mode: this.briefing.mode || 'podcast',
          title: this.briefing.title,
        });
      }
      if (this.clips && this.clips.length) {
        let targetIdx = this.clipIndexAt(this.position);
        const cur = this.audio;
        const curTime = cur ? cur.currentTime : 0;
        const curDur = cur ? (cur.duration || 0) : 0;

        // If the current clip ended or is within 0.2s of its end, advance to the next clip
        if (curDur > 0 && curTime >= curDur - 0.2 && targetIdx + 1 < this.clips.length) {
          targetIdx += 1;
          this.loadClip(targetIdx, { seek: 0, autoplay: true, forceReload: true });
          return;
        }

        // If target clip is not current or audio doesn't have it loaded or is in error
        if (targetIdx !== this.index || cur.dataset.clip !== String(targetIdx) || !cur.src || cur.error) {
          const seek = Math.max(0, this.position - (this.clips[targetIdx]?.start || 0));
          this.loadClip(targetIdx, { seek, autoplay: true, forceReload: true });
          return;
        }
      }
      const p = this.audio.play();
      if (p && typeof p.catch === 'function') {
        p.catch((err) => {
          console.warn('[player] direct play rejected, force reloading active clip:', err);
          if (this.clips && this.clips.length) {
            const targetIdx = this.clipIndexAt(this.position);
            const seek = Math.max(0, this.position - (this.clips[targetIdx]?.start || 0));
            this.loadClip(targetIdx, { seek, autoplay: true, forceReload: true });
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
    if (typeof window !== 'undefined') {
      window.trackEvent?.('play_story', {
        story_id: id,
        title: ch.title,
        section: ch.section,
      });
    }
    this.seekTo(ch.start);
    this.audio.play().catch(() => {});
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
    const story = this.currentStory();
    const b = this.briefing;
    if (story && b?.stories?.length) {
      const idx = b.stories.indexOf(story);
      if (idx >= 0 && idx < b.stories.length - 1) {
        const nextStory = b.stories[idx + 1];
        this.playChapter(nextStory.id);
        return;
      }
    }
    const ch = this.currentChapter();
    const i = this.chapters.indexOf(ch);
    if (i >= 0 && i < this.chapters.length - 1) this.playChapter(this.chapters[i + 1].id);
  }

  prevChapter() {
    const ch = this.currentChapter();
    if (ch && this.position - ch.start > 3) {
      this.playChapter(ch.id);
      return;
    }
    const story = this.currentStory();
    const b = this.briefing;
    if (story && b?.stories?.length) {
      const idx = b.stories.indexOf(story);
      if (idx > 0) {
        const prevStory = b.stories[idx - 1];
        this.playChapter(prevStory.id);
        return;
      }
    }
    const i = this.chapters.indexOf(ch);
    if (i > 0) {
      this.playChapter(this.chapters[i - 1].id);
    } else {
      this.seekTo(0);
    }
  }

  restart() {
    this.seekTo(0);
    if (!this.isPlaying) {
      this.toggle();
    }
    this.tick();
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

  setupCardSwipe() {
    if (typeof document === 'undefined') return;
    const card = document.getElementById('cleanPlayerCard');
    const rearCard = document.getElementById('cleanCardStackBg');
    const bg2 = document.getElementById('cleanCardStackBg2');
    const deckWrap = document.getElementById('cleanDeckWrap');
    if (!card) return;

    const BASE_FRONT_X = -8;
    const BASE_REAR_X = 10;
    const BASE_REAR_SCALE = 0.95;
    const BASE_REAR_OPACITY = 0.70;
    const BASE_L2_X = 14;
    const BASE_L2_SCALE = 0.90;
    const BASE_L2_OPACITY = 0.30;

    let startX = 0;
    let startY = 0;
    let startTime = 0;
    let isTracking = false;
    let isLockedVertical = false;
    let isLockedHorizontal = false;
    let currentDeltaX = 0;

    const getBaseFrontX = () => (deckWrap?.classList.contains('is-last-card') ? 0 : BASE_FRONT_X);

    const onPointerDown = (e) => {
      // Do not initiate card swipe if clicking buttons, links, scrubber, or interactive controls
      if (e.target.closest('.clean-card-bottom-dock, .clean-cover-actions, .clean-source-link, button, a, [role="slider"], input, select, textarea')) {
        return;
      }
      isTracking = true;
      isLockedVertical = false;
      isLockedHorizontal = false;
      startX = e.clientX ?? (e.touches && e.touches[0]?.clientX) ?? 0;
      startY = e.clientY ?? (e.touches && e.touches[0]?.clientY) ?? 0;
      startTime = Date.now();
      currentDeltaX = 0;
    };

    const onPointerMove = (e) => {
      if (!isTracking || isLockedVertical) return;

      const clientX = e.clientX ?? (e.touches && e.touches[0]?.clientX) ?? 0;
      const clientY = e.clientY ?? (e.touches && e.touches[0]?.clientY) ?? 0;
      const deltaX = clientX - startX;
      const deltaY = clientY - startY;

      if (!isLockedHorizontal) {
        // If vertical movement dominates, lock to vertical scrolling for teleprompter reading
        if (Math.abs(deltaY) > Math.abs(deltaX) && Math.abs(deltaY) > 7) {
          isLockedVertical = true;
          return;
        }
        // If horizontal movement is intentional, lock to horizontal card swipe
        if (Math.abs(deltaX) > Math.abs(deltaY) + 4 && Math.abs(deltaX) > 7) {
          isLockedHorizontal = true;
          card.style.transition = 'none';
          if (rearCard) rearCard.style.transition = 'none';
          if (bg2) bg2.style.transition = 'none';
        } else {
          return;
        }
      }

      if (e.cancelable) {
        e.preventDefault();
      }

      const story = this.currentStory();
      const b = this.briefing;
      const ch = this.currentChapter();
      const storyIdx = (story && b?.stories) ? b.stories.indexOf(story) : -1;
      const canGoNext = storyIdx >= 0 ? storyIdx < b.stories.length - 1 : Boolean(this.chapters.indexOf(ch) < this.chapters.length - 1);
      const canGoPrev = storyIdx > 0 || (story && this.position - (story.start || 0) > 3) || (ch && this.position - ch.start > 3);

      // Rubberband resistance if boundary reached
      let effectiveDeltaX = deltaX;
      if (deltaX < 0 && !canGoNext) {
        effectiveDeltaX = deltaX * 0.22;
      } else if (deltaX > 0 && !canGoPrev) {
        effectiveDeltaX = deltaX * 0.22;
      }
      currentDeltaX = effectiveDeltaX;

      const cardWidth = card.clientWidth || 360;
      const rotation = (effectiveDeltaX / cardWidth) * 9;
      const baseFront = getBaseFrontX();
      card.style.transform = `translateX(${baseFront + effectiveDeltaX}px) rotate(${rotation}deg)`;

      if (effectiveDeltaX < 0 && canGoNext) {
        // Swiping Left: Front card moves out to left, rear card steps IN from the right (+10px -> 0px) and scales up to 1.0!
        const progress = Math.min(1, Math.abs(effectiveDeltaX) / 130);
        if (rearCard) {
          const rX = BASE_REAR_X * (1 - progress);
          const rScale = BASE_REAR_SCALE + (1 - BASE_REAR_SCALE) * progress;
          const rOp = BASE_REAR_OPACITY + (1 - BASE_REAR_OPACITY) * progress;
          rearCard.style.transform = `translateX(${rX}px) scale(${rScale})`;
          rearCard.style.opacity = String(rOp);
        }
        if (bg2) {
          const lX = BASE_L2_X - (BASE_L2_X - BASE_REAR_X) * progress;
          const lScale = BASE_L2_SCALE + (BASE_REAR_SCALE - BASE_L2_SCALE) * progress;
          const lOp = BASE_L2_OPACITY + (BASE_REAR_OPACITY - BASE_L2_OPACITY) * progress;
          bg2.style.transform = `translateX(${lX}px) scale(${lScale})`;
          bg2.style.opacity = String(lOp);
        }
      } else if (effectiveDeltaX > 0 && canGoPrev) {
        // Swiping Right: Front card moves right
        if (rearCard) {
          rearCard.style.opacity = String(Math.max(0.2, BASE_REAR_OPACITY - (effectiveDeltaX / 120) * 0.4));
        }
      }
    };

    const onPointerUp = () => {
      if (!isTracking) return;
      isTracking = false;

      if (!isLockedHorizontal) return;
      isLockedHorizontal = false;

      const elapsed = Date.now() - startTime;
      const velocity = Math.abs(currentDeltaX) / Math.max(elapsed, 1);
      const passedThreshold = Math.abs(currentDeltaX) > 55 || (velocity > 0.32 && Math.abs(currentDeltaX) > 22);

      const story = this.currentStory();
      const b = this.briefing;
      const ch = this.currentChapter();
      const storyIdx = (story && b?.stories) ? b.stories.indexOf(story) : -1;
      const canGoNext = storyIdx >= 0 ? storyIdx < b.stories.length - 1 : Boolean(this.chapters.indexOf(ch) < this.chapters.length - 1);
      const canGoPrev = storyIdx > 0 || (story && this.position - (story.start || 0) > 3) || (ch && this.position - ch.start > 3);

      if (currentDeltaX < -20 && passedThreshold && canGoNext) {
        // Swiped Left -> Animate front card OUT to left, rear card IN to center
        card.style.transition = 'transform 0.24s cubic-bezier(0.2, 0.9, 0.3, 1), opacity 0.22s ease';
        card.style.transform = 'translateX(-120%) rotate(-10deg)';
        card.style.opacity = '0';

        if (rearCard) {
          rearCard.style.transition = 'transform 0.24s cubic-bezier(0.2, 0.9, 0.3, 1), opacity 0.22s ease';
          rearCard.style.transform = 'translateX(0px) scale(1)';
          rearCard.style.opacity = '1';
        }
        if (bg2) {
          bg2.style.transition = 'transform 0.24s cubic-bezier(0.2, 0.9, 0.3, 1), opacity 0.22s ease';
          bg2.style.transform = `translateX(${BASE_REAR_X}px) scale(${BASE_REAR_SCALE})`;
          bg2.style.opacity = String(BASE_REAR_OPACITY);
        }

        setTimeout(() => {
          this.nextChapter();
          // Front card seamlessly takes over at baseFront with full opacity (no popping or reverse jump)
          const baseFront = getBaseFrontX();
          card.style.transition = 'none';
          card.style.transform = `translateX(${baseFront}px)`;
          card.style.opacity = '1';

          // Reset rear card and bg2 to their back stack positions
          if (rearCard) {
            rearCard.style.transition = 'none';
            rearCard.style.transform = `translateX(${BASE_REAR_X}px) scale(${BASE_REAR_SCALE})`;
            rearCard.style.opacity = String(BASE_REAR_OPACITY);
          }
          if (bg2) {
            bg2.style.transition = 'none';
            bg2.style.transform = `translateX(${BASE_L2_X}px) scale(${BASE_L2_SCALE})`;
            bg2.style.opacity = String(BASE_L2_OPACITY);
          }
        }, 240);
      } else if (currentDeltaX > 20 && passedThreshold && canGoPrev) {
        // Swiped Right -> Pull previous story IN from the left, step current story down into rear stack
        // 1. Immediately switch playback to previous story so DOM content updates
        this.prevChapter();

        // 2. Position front card off-screen to the left (where it was previously dealt)
        card.style.transition = 'none';
        card.style.transform = 'translateX(-110%) rotate(-8deg)';
        card.style.opacity = '0.9';

        // 3. Position rear card at center (displaying the story that was just on front)
        if (rearCard) {
          rearCard.style.transition = 'none';
          rearCard.style.transform = 'translateX(0px) scale(1)';
          rearCard.style.opacity = '1';
        }
        if (bg2) {
          bg2.style.transition = 'none';
          bg2.style.transform = `translateX(${BASE_REAR_X}px) scale(${BASE_REAR_SCALE})`;
          bg2.style.opacity = String(BASE_REAR_OPACITY);
        }

        // Force browser reflow to commit initial positions before triggering animation
        void card.offsetWidth;

        // 4. Animate front card gliding in smoothly from the left into center
        const baseFront = getBaseFrontX();
        card.style.transition = 'transform 0.28s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.24s ease';
        card.style.transform = `translateX(${baseFront}px) rotate(0deg)`;
        card.style.opacity = '1';

        // 5. Animate rear card settling back down into its back-stack rest position
        if (rearCard) {
          rearCard.style.transition = 'transform 0.28s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.24s ease';
          rearCard.style.transform = `translateX(${BASE_REAR_X}px) scale(${BASE_REAR_SCALE})`;
          rearCard.style.opacity = String(BASE_REAR_OPACITY);
        }
        if (bg2) {
          bg2.style.transition = 'transform 0.28s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.24s ease';
          bg2.style.transform = `translateX(${BASE_L2_X}px) scale(${BASE_L2_SCALE})`;
          bg2.style.opacity = String(BASE_L2_OPACITY);
        }
      } else {
        // Snap back to active rest position
        const baseFront = getBaseFrontX();
        card.style.transition = 'transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s ease';
        card.style.transform = `translateX(${baseFront}px)`;
        card.style.opacity = '1';

        if (rearCard) {
          rearCard.style.transition = 'transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s ease';
          rearCard.style.transform = `translateX(${BASE_REAR_X}px) scale(${BASE_REAR_SCALE})`;
          rearCard.style.opacity = String(BASE_REAR_OPACITY);
        }
        if (bg2) {
          bg2.style.transition = 'transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s ease';
          bg2.style.transform = `translateX(${BASE_L2_X}px) scale(${BASE_L2_SCALE})`;
          bg2.style.opacity = String(BASE_L2_OPACITY);
        }
      }
    };

    // Attach passive touch and pointer events
    card.addEventListener('touchstart', onPointerDown, { passive: true });
    card.addEventListener('touchmove', onPointerMove, { passive: false });
    card.addEventListener('touchend', onPointerUp, { passive: true });
    card.addEventListener('touchcancel', onPointerUp, { passive: true });
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
      b.addEventListener?.('click', () => this.setRate(s));
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
    if (this.audio) this.audio.playbackRate = rate;
    if (this.briefing?.mode !== 'rapid') {
      store.set('rate', rate);
    }
    this.syncSpeedPills();
    this.syncPositionState();
    try {
      window.dispatchEvent(new CustomEvent('playbackspeedchange', { detail: { speed: rate } }));
    } catch {}
  }

  setPlaying(on) {
    if (on) {
      this.requestWakeLock();
    } else {
      this.releaseWakeLock();
    }
    document.body.classList.toggle('playing', on);
    if (this.hero) this.hero.classList.toggle('playing-now', on);
    if (this.el?.play) this.el.play.setAttribute('aria-label', on ? 'Pause briefing' : 'Play briefing');
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = on ? 'playing' : 'paused';
    const liveStatus = document.getElementById('liveStatus');
    if (liveStatus) liveStatus.textContent = on ? 'Playing' : 'Paused';
    if (typeof window !== 'undefined' && window.HarkNative) {
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
    const frac = dur ? Math.min(1, Math.max(0, t / dur)) : 0;
    if (t > 0 && Math.round(t) % 5 === 0) {
      const posKey = posKeyFor(b);
      store.set(posKey, t);
      this.syncPositionState();
    }

    if (typeof document === 'undefined') return;

    // Segments + thumb.
    if (el.seg && typeof el.seg.querySelectorAll === 'function') {
      const segs = el.seg.querySelectorAll('.seg');
      this.segments.forEach((s, i) => {
        const f = s.end > s.start ? Math.min(1, Math.max(0, (t - s.start) / (s.end - s.start))) : 0;
        const fill = segs[i]?.firstChild;
        if (fill) fill.style.width = `${f * 100}%`;
      });
      if (el.thumb) el.thumb.style.left = `${frac * 100}%`;
      el.seg.setAttribute('aria-valuenow', String(Math.round(frac * 100)));
    }

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
    const isIntroOrBanter = Boolean(ch && (
      (typeof ch.id === 'string' && (
        ch.id.startsWith('pod_open') ||
        ch.id.startsWith('pod_tease') ||
        ch.id.startsWith('pod_bridge') ||
        ch.id.startsWith('greeting') ||
        ch.id.startsWith('pod_close') ||
        ch.id === 'outro'
      )) || ch.kind === 'note'
    ));
    const started = t >= 0.5;
    if (el.state) {
      el.state.textContent = !started && !this.isPlaying
        ? `Ready · ${b.stories.length} ${b.stories.length === 1 ? 'story' : 'stories'}`
        : (this.isPlaying ? 'Now playing' : 'Paused');
    }
    if (el.title) {
      el.title.textContent = (isIntroOrBanter && ch?.title)
        ? ch.title
        : (story?.headline || ch?.title || b.stories?.[0]?.headline || b.title);
    }

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
        const span = readerArticleLink.querySelector?.('span');
        if (span) span.textContent = `Full story on ${srcName}`;
        readerArticleLink.classList?.remove?.('hidden');
      } else {
        readerArticleLink.classList?.add?.('hidden');
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
      const text = isIntroOrBanter
        ? (ch?.text || ch?.title || '')
        : (story?.script || story?.summary || story?.headline || ch?.text || ch?.title || b.stories?.[0]?.script || b.stories?.[0]?.summary || '');
      if (text) {
        transBox.classList.remove('hidden');
        const currentId = isIntroOrBanter ? (ch?.id || '') : (story?.id || ch?.id || '');
        if (transText.dataset.storyId !== currentId) {
          transText.dataset.storyId = currentId;
          transBody.scrollTop = 0;

          const dialogueTurns = parseDialogueTurns(text);
          if (dialogueTurns && dialogueTurns.length) {
            let cumFractions;
            const chDur = Math.max(0.1, (ch?.end || dur) - (ch?.start || 0));
            if (Array.isArray(story?.marks) && story.marks.length === dialogueTurns.length) {
              // Real millisecond turn timestamps from voice engine (Item T1)
              cumFractions = story.marks.map((m) => ({
                start: Math.max(0, Math.min(1, (Number(m.start) || 0) / chDur)),
                end: Math.max(0, Math.min(1, (Number(m.end) || 0) / chDur)),
              }));
            } else {
              // Pause-weighted teleprompter estimate fallback for legacy stories (Item T2)
              const PAUSE_CHAR_EQUIV = 6.0;
              const weights = dialogueTurns.map((turn) => Math.max(1, turn.text.length + PAUSE_CHAR_EQUIV));
              const totalWeight = weights.reduce((a, b) => a + b, 0);
              let running = 0;
              cumFractions = weights.map((w) => {
                const start = running / totalWeight;
                running += w;
                return { start, end: running / totalWeight };
              });
            }

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
    // During intro chat, host banter, or outro sign-off, show the category SVG artwork.
    // When a story is playing, show the story's editorial image (or category default SVG fallback).
    let img = null;
    if (isIntroOrBanter) {
      const secKey = (ch?.section || story?.section || this.currentSection || '').replace(/_(us|in|ca)$/, '');
      img = getDefaultCover(secKey);
    } else if (story?.image) {
      img = story.image;
    } else {
      const upNext = this.chapters.find((c) => c.kind === 'story' && c.start >= t - 0.01);
      img = (story || this.storyFor(upNext))?.image || null;
    }

    const currentSec = story?.section || section || this.currentSection || 'top';
    const fallbackCover = getDefaultCover(currentSec);
    const effectiveImg = (img && !this.failedImages.has(img)) ? img : fallbackCover;

    if (effectiveImg && el.cover && el.cover.dataset.src !== effectiveImg) {
      el.cover.dataset.src = effectiveImg;
      el.cover.src = effectiveImg;
      el.cover.classList.remove('hidden');
    } else if (!effectiveImg && el.cover) {
      el.cover.classList.add('hidden');
    }

    // Update Big Picture in the story reader
    const readerImg = document.getElementById('readerHeroImage');
    if (readerImg) {
      if (effectiveImg && readerImg.dataset.src !== effectiveImg) {
        readerImg.dataset.src = effectiveImg;
        readerImg.src = effectiveImg;
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
    if (cleanCoverImg) {
      if (cleanCoverImg.dataset.src !== effectiveImg) {
        cleanCoverImg.dataset.src = effectiveImg;
        cleanCoverImg.src = effectiveImg;
      }
      cleanCoverImg.classList.remove('hidden');
      cleanCoverFallback?.classList.add('hidden');
    }
    if (ambientBackdrop) {
      if (ambientBackdrop.dataset.bg !== effectiveImg) {
        ambientBackdrop.dataset.bg = effectiveImg;
        ambientBackdrop.style.backgroundImage = `url("${effectiveImg}")`;
        ambientBackdrop.classList.add('has-image');
      }
    }

    const cleanNowVoicing = document.getElementById('playerCoverBadgeText');
    if (cleanNowVoicing) {
      if (isIntroOrBanter) {
        cleanNowVoicing.textContent = 'AI Duo · Matthew & Kelly';
      } else if (activeSpeaker) {
        cleanNowVoicing.textContent = `AI Duo · ${activeSpeaker}`;
      } else if (this.briefing?.mode === 'podcast') {
        cleanNowVoicing.textContent = 'AI Duo · Matthew & Kelly';
      } else {
        cleanNowVoicing.textContent = 'Now voicing';
      }
    }

    // Clean Player Story Metadata & Actions
    const cleanCat = document.getElementById('cleanCatBadge');
    if (cleanCat) {
      let catText = 'TOP STORIES';
      if (isIntroOrBanter) {
        if (ch?.id?.startsWith('pod_open') || ch?.id?.startsWith('greeting')) {
          catText = 'PREVIEW';
        } else if (ch?.id?.startsWith('pod_close') || ch?.id === 'outro') {
          catText = 'SIGN-OFF';
        } else {
          const secKey = ch?.section || story?.section || section;
          catText = (secKey || 'UP NEXT').replace(/_(us|in|ca)$/, '');
        }
      } else {
        catText = ch?.section || section || story?.section || b.stories?.[0]?.section || 'TOP STORIES';
      }
      cleanCat.textContent = catText.toUpperCase();
    }
    const cleanSrc = document.getElementById('cleanSourceTitle');
    if (cleanSrc) {
      if (isIntroOrBanter) {
        cleanSrc.textContent = 'Hark Daily';
      } else {
        const srcRaw = story?.source || b.stories?.[0]?.source;
        cleanSrc.textContent = srcRaw ? srcRaw.split('·')[0].trim() : 'Daily News';
      }
    }
    const cleanCounter = document.getElementById('cleanStoryCounter');
    if (cleanCounter) {
      const idx = story ? b.stories.indexOf(story) + 1 : 1;
      cleanCounter.textContent = `${idx} / ${b.stories?.length || 1}`;
      const deckWrap = document.getElementById('cleanDeckWrap');
      if (deckWrap) {
        const isLast = idx >= (b.stories?.length || 1);
        deckWrap.classList.toggle('is-last-card', Boolean(isLast));
      }

      // Populate Peeking Rear Card Preview (Up Next Story)
      const currentStoryIdx = story ? b.stories.indexOf(story) : 0;
      const nextStory = b.stories?.[currentStoryIdx + 1];
      if (nextStory) {
        const rearCoverImg = document.getElementById('rearCoverImg');
        if (rearCoverImg) {
          const nextSec = nextStory.section || 'top';
          const nextImg = (nextStory.image && !this.failedImages.has(nextStory.image))
            ? nextStory.image
            : (nextStory.image_url || getDefaultCover(nextSec));
          if (rearCoverImg.dataset.src !== nextImg) {
            rearCoverImg.dataset.src = nextImg;
            rearCoverImg.src = nextImg;
          }
        }
        // Preload next-next story image in browser cache so rapid successive swipes are instant
        const afterNext = b.stories?.[currentStoryIdx + 2];
        if (afterNext?.image && !this.failedImages.has(afterNext.image)) {
          const prefetch = new Image();
          prefetch.src = afterNext.image;
        }
        const rearCat = document.getElementById('rearCatBadge');
        if (rearCat) {
          rearCat.textContent = (nextStory.section || 'TOP STORIES').toUpperCase();
        }
        const rearSrc = document.getElementById('rearSourceTitle');
        if (rearSrc) {
          const srcRaw = nextStory.source;
          rearSrc.textContent = srcRaw ? srcRaw.split('·')[0].trim() : 'Up Next';
        }
        const rearCounter = document.getElementById('rearStoryCounter');
        if (rearCounter) {
          rearCounter.textContent = `${currentStoryIdx + 2} / ${b.stories?.length || 1}`;
        }
        const rearHeadline = document.getElementById('rearStoryHeadline');
        if (rearHeadline) {
          rearHeadline.textContent = nextStory.headline || 'Next story';
        }
        const rearSnippet = document.getElementById('rearSnippet');
        if (rearSnippet) {
          rearSnippet.textContent = nextStory.summary || nextStory.content?.slice(0, 120) || 'Up next on Hark Daily…';
        }
      }
    }
    const cleanHeadline = document.getElementById('cleanStoryHeadline');
    if (cleanHeadline) {
      cleanHeadline.textContent = (isIntroOrBanter && ch?.title)
        ? ch.title
        : (story?.headline || ch?.title || b.stories?.[0]?.headline || b.title);
    }

    const cleanShare = document.getElementById('cleanShareBtn');
    if (cleanShare && (story || b.stories?.[0])) {
      cleanShare.onclick = (e) => {
        e.stopPropagation();
        window.openShareModal?.(story || b.stories[0]);
      };
    }

    const cleanReport = document.getElementById('cleanReportBtn');
    if (cleanReport && (story || b.stories?.[0])) {
      cleanReport.onclick = (e) => {
        e.stopPropagation();
        window.openFeedbackModal?.({ story: story || b.stories[0], category: '🎙️ Audio' });
      };
    }

    const cleanSourceLink = document.getElementById('cleanSourceLink');
    const cleanSourceLinkName = document.getElementById('cleanSourceLinkName');
    if (cleanSourceLink) {
      if (isIntroOrBanter) {
        cleanSourceLink.classList.add('hidden');
      } else {
        const sTarget = story || b.stories?.[0];
        if (sTarget?.url) {
          cleanSourceLink.href = sTarget.url;
          const srcName = sTarget?.source ? sTarget.source.split('·')[0].trim() : 'original source';
          if (cleanSourceLinkName) cleanSourceLinkName.textContent = `Read on ${srcName}`;
          cleanSourceLink.classList.remove('hidden');
        } else {
          cleanSourceLink.classList.add('hidden');
        }
      }
    }

    // Floating Mini player docked above toolbar
    if (el.miniTitle) el.miniTitle.textContent = story?.headline || ch?.title || b.stories?.[0]?.headline || b.title;
    if (el.miniSub) el.miniSub.textContent = [section, `${fmtTime(t)} / ${fmtTime(dur)}`].filter(Boolean).join(' · ');
    if (el.miniBar) el.miniBar.style.width = `${frac * 100}%`;
    if (effectiveImg && el.miniCover && el.miniCover.dataset.src !== effectiveImg) {
      el.miniCover.dataset.src = effectiveImg;
      el.miniCover.src = effectiveImg;
      el.miniCover.classList.remove('hidden');
      el.miniEq?.classList.add('hidden');
    } else if (!effectiveImg && el.miniCover) {
      el.miniCover.classList.add('hidden');
      el.miniEq?.classList.remove('hidden');
    }
    this.showMini();

    if (ch && ch.id !== this.current && (t > 0 || this.isPlaying)) {
      this.current = ch.id;
      this.updateMediaSession(ch, story);
      this.dispatchEvent(new CustomEvent('chapter', { detail: ch }));
    }
  }

  updateMediaSession(ch, story) {
    if (typeof window !== 'undefined' && window.HarkNative && this.isPlaying) {
      try {
        const title = ch?.title || story?.headline || this.briefing?.title || 'Hark Daily';
        const artist = 'Hark Daily \u2022 ' + (this.briefing?.title || 'Briefing');
        window.HarkNative.notifyPlaybackState(true, title, artist);
      } catch {}
    }
    if (!('mediaSession' in navigator)) return;
    const coverSrc = (story?.image && !this.failedImages.has(story.image))
      ? story.image
      : getDefaultCover(story?.section || this.currentSection);
    const art = [{ src: coverSrc, sizes: '512x512' }];
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
