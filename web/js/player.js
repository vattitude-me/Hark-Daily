// Audio player with chapters, lock-screen controls and resume.
import { fmtTime, h, store } from './api.js';

const SPEEDS = [1, 1.25, 1.5, 0.85];

export class Player extends EventTarget {
  constructor() {
    super();
    this.audio = document.getElementById('audio');
    this.hero = document.getElementById('hero');
    this.el = {
      play: document.getElementById('playBtn'),
      seek: document.getElementById('seek'),
      fill: document.getElementById('trackFill'),
      marks: document.getElementById('trackMarks'),
      cur: document.getElementById('curTime'),
      dur: document.getElementById('durTime'),
      label: document.getElementById('npLabel'),
      title: document.getElementById('npTitle'),
      speed: document.getElementById('speedBtn'),
      mini: document.getElementById('miniPlayer'),
      miniTitle: document.getElementById('miniTitle'),
      miniBar: document.getElementById('miniBar'),
    };
    this.briefing = null;
    this.chapters = [];
    this.current = null;
    this.speed = store.get('rate', 1);
    this.bind();
  }

  bind() {
    const { audio, el } = this;
    el.play.addEventListener('click', () => this.toggle());
    document.getElementById('miniPlay').addEventListener('click', () => this.toggle());
    document.getElementById('back15').addEventListener('click', () => this.skip(-15));
    document.getElementById('fwd30').addEventListener('click', () => this.skip(30));
    document.getElementById('nextChapter').addEventListener('click', () => this.nextChapter());
    document.getElementById('miniNext').addEventListener('click', () => this.nextChapter());
    document.getElementById('prevChapter').addEventListener('click', () => this.prevChapter());
    el.speed.addEventListener('click', () => {
      const i = (SPEEDS.indexOf(this.speed) + 1) % SPEEDS.length;
      this.setRate(SPEEDS[i]);
    });
    el.seek.addEventListener('input', () => {
      if (audio.duration) audio.currentTime = (el.seek.value / 1000) * audio.duration;
    });

    audio.addEventListener('timeupdate', () => this.tick());
    audio.addEventListener('loadedmetadata', () => {
      el.dur.textContent = fmtTime(audio.duration);
      this.drawMarks();
      audio.playbackRate = this.speed;
    });
    audio.addEventListener('play', () => this.setPlaying(true));
    audio.addEventListener('pause', () => this.setPlaying(false));
    audio.addEventListener('ended', () => {
      this.setPlaying(false);
      store.set(`pos-${this.briefing?.date}`, 0);
      el.label.textContent = 'Finished';
      el.title.textContent = "That's today's briefing. Have a great day!";
    });

    // Show the floating mini player once the hero scrolls away.
    new IntersectionObserver(([entry]) => {
      const show = !entry.isIntersecting && this.briefing && (this.isPlaying || audio.currentTime > 0);
      el.mini.classList.toggle('show', !!show);
      el.mini.setAttribute('aria-hidden', show ? 'false' : 'true');
    }, { threshold: 0.05 }).observe(this.hero);

    if ('mediaSession' in navigator) {
      const ms = navigator.mediaSession;
      ms.setActionHandler('play', () => audio.play());
      ms.setActionHandler('pause', () => audio.pause());
      ms.setActionHandler('seekbackward', () => this.skip(-15));
      ms.setActionHandler('seekforward', () => this.skip(30));
      ms.setActionHandler('previoustrack', () => this.prevChapter());
      ms.setActionHandler('nexttrack', () => this.nextChapter());
      try { ms.setActionHandler('seekto', (d) => { audio.currentTime = d.seekTime; }); } catch { /* unsupported */ }
    }
    this.el.speed.textContent = `${this.speed}×`;
  }

  get isPlaying() { return !this.audio.paused && !this.audio.ended; }

  load(briefing) {
    this.briefing = briefing;
    this.chapters = briefing.chapters.filter((c) => c.kind !== 'section');
    this.current = null;
    this.audio.src = briefing.audio_url;
    this.el.label.textContent = 'Ready when you are';
    this.el.title.textContent = `Press play for ${briefing.stories.length} stories · ${Math.round(briefing.duration / 60)} min`;
    const saved = store.get(`pos-${briefing.date}`, 0);
    if (saved > 5 && saved < briefing.duration - 5) {
      this.audio.addEventListener('loadedmetadata', () => { this.audio.currentTime = saved; }, { once: true });
      this.el.label.textContent = 'Pick up where you left off';
    }
    this.tick();
  }

  toggle() {
    if (!this.briefing) return;
    if (this.isPlaying) this.audio.pause();
    else this.audio.play().catch(() => {});
  }

  skip(sec) {
    if (!this.briefing) return;
    this.audio.currentTime = Math.min(Math.max(0, this.audio.currentTime + sec), this.audio.duration || 0);
  }

  playChapter(id) {
    const ch = this.chapters.find((c) => c.id === id);
    if (!ch) return;
    this.audio.currentTime = ch.start;
    this.audio.play().catch(() => {});
  }

  chapterIndex(t = this.audio.currentTime) {
    let idx = 0;
    this.chapters.forEach((c, i) => { if (t >= c.start - 0.05) idx = i; });
    return idx;
  }

  nextChapter() {
    const i = this.chapterIndex();
    if (i < this.chapters.length - 1) this.playChapter(this.chapters[i + 1].id);
  }

  prevChapter() {
    const i = this.chapterIndex();
    const ch = this.chapters[i];
    // Like a music player: first tap restarts the story, second goes back one.
    if (ch && this.audio.currentTime - ch.start > 3) this.playChapter(ch.id);
    else if (i > 0) this.playChapter(this.chapters[i - 1].id);
  }

  setRate(rate) {
    this.speed = rate;
    this.audio.playbackRate = rate;
    this.el.speed.textContent = `${rate}×`;
    store.set('rate', rate);
  }

  setPlaying(on) {
    document.body.classList.toggle('playing', on);
    this.hero.classList.toggle('playing', on);
    this.el.mini.classList.toggle('playing', on);
    this.el.play.setAttribute('aria-label', on ? 'Pause briefing' : 'Play briefing');
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = on ? 'playing' : 'paused';
    this.dispatchEvent(new CustomEvent('state', { detail: { playing: on } }));
  }

  drawMarks() {
    const dur = this.audio.duration || this.briefing?.duration;
    this.el.marks.replaceChildren(
      ...this.briefing.chapters
        .filter((c) => c.kind === 'story' || c.kind === 'section')
        .map((c) => h('i', { class: c.kind === 'section' ? 'section' : '', style: `left:${(c.start / dur) * 100}%` })),
    );
  }

  tick() {
    const { audio, el } = this;
    const dur = audio.duration || this.briefing?.duration || 0;
    const pct = dur ? (audio.currentTime / dur) * 100 : 0;
    el.fill.style.width = `${pct}%`;
    el.miniBar.style.width = `${pct}%`;
    el.seek.value = Math.round(pct * 10);
    el.cur.textContent = fmtTime(audio.currentTime);
    if (!this.chapters.length) return;
    if (audio.currentTime > 0 && Math.round(audio.currentTime) % 5 === 0) {
      store.set(`pos-${this.briefing.date}`, audio.currentTime);
    }

    const ch = this.chapters[this.chapterIndex()];
    if (ch && ch.id !== this.current && (audio.currentTime > 0 || this.isPlaying)) {
      this.current = ch.id;
      const storyNo = this.chapters.filter((c) => c.kind === 'story').findIndex((c) => c.id === ch.id) + 1;
      const total = this.briefing.stories.length;
      el.label.textContent = ch.kind === 'story' ? `Story ${storyNo} of ${total}` : 'Now playing';
      el.title.textContent = ch.title;
      el.miniTitle.textContent = ch.title;
      this.updateMediaSession(ch);
      this.dispatchEvent(new CustomEvent('chapter', { detail: ch }));
    }
  }

  updateMediaSession(ch) {
    if (!('mediaSession' in navigator)) return;
    const story = this.briefing.stories.find((s) => s.id === ch.id);
    const art = story?.image ? [{ src: story.image, sizes: '512x512' }] : [];
    navigator.mediaSession.metadata = new MediaMetadata({
      title: ch.title,
      artist: 'Morning Brief',
      album: this.briefing.title,
      artwork: [...art, { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' }],
    });
  }
}
