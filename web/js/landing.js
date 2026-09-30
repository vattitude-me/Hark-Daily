// Signed-out landing: play today's real sample, show its headlines and voices, then sign in.
import { api, h, store } from './api.js';

const SECTION = { canada: ['🇨🇦', 'Canada'], tech: ['🤖', 'AI & Tech'], custom: ['⭐', 'My Sources'] };
const $ = (id) => document.getElementById(id);

export class Landing {
  constructor({ onSignedIn }) {
    this.onSignedIn = onSignedIn;
    this.audio = $('sampleAudio');
    this.voiceAudio = new Audio();
    this.email = '';
    this.bindPlayer();
    this.bindSignIn();
  }

  async show() {
    const hr = new Date().getHours();
    $('lgGreeting').textContent = hr < 12 ? 'Good morning' : hr < 17 ? 'Good afternoon' : 'Good evening';
    this.checkLinkError();
    let data = {};
    try { data = await api.showcase(); } catch { /* table missing or offline: use the bundled sample */ }
    if (!data.briefing?.audio_url) {
      try { data = await (await fetch('/sample/sample.json')).json(); } catch { data = {}; }
    }
    this.render(data);
  }

  // ------------------------------------------------------------------ sample
  render({ briefing, voices }) {
    this.briefing = briefing;
    const player = $('samplePlayer');
    if (!briefing?.audio_url) {
      player.classList.add('disabled');
      $('samplePlay').disabled = true;
      $('sampleLabel').textContent = 'Sample coming soon';
      $('sampleTitle').textContent = "Today's sample is being prepared. Check back in a few minutes.";
    } else {
      const mins = Math.max(1, Math.round(briefing.duration / 60));
      const today = briefing.date === new Date().toLocaleDateString('en-CA');
      $('sampleLabel').textContent = `${today ? "Today's top stories" : 'Sample briefing'} · ${mins} min`;
      $('sampleTitle').textContent = today ? "Tap play to hear this morning's brief" : 'Tap play to hear a real morning brief';
      if (!today) $('sampleHeading').textContent = 'Headlines from a recent brief';
      $('sampleDate').textContent = today ? `${briefing.title} · the same stories you'd hear` : `From ${briefing.title}`;
      $('sampleCards').replaceChildren(...briefing.stories.map((s) => this.card(s)));
      $('sampleSection').hidden = false;
    }
    const list = (voices || []).slice(0, 8);
    if (list.length) {
      $('sampleVoices').replaceChildren(...list.map((v) => this.voiceChip(v)));
      $('voiceSection').hidden = false;
    }
  }

  card(s) {
    const [emoji, label] = SECTION[s.section] || SECTION.custom;
    const media = s.image
      ? h('div', { class: 'card-media' }, h('img', {
        src: s.image, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer',
        onerror: (e) => e.target.parentElement.replaceWith(this.placeholder(s.section, emoji)),
      }))
      : this.placeholder(s.section, emoji);
    media.append(h('span', { class: 'chip', dataset: { section: s.section } }, label));
    return h('article', { class: 'sample-card', dataset: { id: s.id } },
      media,
      h('div', { class: 'card-body' },
        h('span', { class: 'meta' }, s.source),
        h('h3', {}, s.headline),
        h('p', {}, s.summary)));
  }

  placeholder(section, emoji) {
    return h('div', { class: 'card-media placeholder', dataset: { section } }, h('span', { 'aria-hidden': 'true' }, emoji));
  }

  bindPlayer() {
    const a = this.audio;
    const player = $('samplePlayer');
    $('samplePlay').addEventListener('click', () => {
      if (!this.briefing?.audio_url) return;
      if (!a.src) a.src = this.briefing.audio_url;
      this.voiceAudio.pause();
      if (a.paused) a.play().catch(() => {}); else a.pause();
    });
    a.addEventListener('play', () => player.classList.add('playing'));
    a.addEventListener('pause', () => player.classList.remove('playing'));
    a.addEventListener('ended', () => {
      $('sampleTitle').textContent = 'That was today. Want your own, every morning?';
      this.highlight(null);
    });
    a.addEventListener('timeupdate', () => {
      const b = this.briefing;
      if (!b) return;
      $('sampleBar').style.width = `${Math.min(100, (a.currentTime / (a.duration || b.duration)) * 100)}%`;
      const ch = b.chapters.find((c) => a.currentTime >= c.start && a.currentTime < c.end && c.kind === 'story');
      const id = ch?.id || null;
      if (id === this.current) return;
      this.current = id;
      if (ch) $('sampleTitle').textContent = ch.title;
      this.highlight(id);
    });
  }

  highlight(id) {
    document.querySelectorAll('.sample-card.reading').forEach((c) => c.classList.remove('reading'));
    if (!id) return;
    const el = document.querySelector(`.sample-card[data-id="${CSS.escape(id)}"]`);
    if (!el) return;
    el.classList.add('reading');
    const row = $('sampleCards');
    row.scrollTo({ left: el.offsetLeft - row.offsetLeft, behavior: 'smooth' });
  }

  voiceChip(v) {
    const chip = h('button', { type: 'button', class: 'voice-chip', 'aria-label': `Hear ${v.name}` },
      h('span', { class: 'avatar' }, v.name[0]),
      h('span', {}, v.name, h('small', {}, [v.accent, v.gender].filter(Boolean).join(' · '))));
    chip.addEventListener('click', () => {
      const va = this.voiceAudio;
      document.querySelectorAll('.voice-chip.playing').forEach((c) => c.classList.remove('playing'));
      if (va.dataset.id === v.id && !va.paused) { va.pause(); return; }
      this.audio.pause();
      va.dataset.id = v.id;
      va.src = v.preview_url;
      va.onended = () => chip.classList.remove('playing');
      va.play().then(() => chip.classList.add('playing')).catch(() => {});
      store.set('pending-voice', v.id); // becomes their voice on first sign-in
    });
    return chip;
  }

  // ----------------------------------------------------------------- sign in
  openSignIn() {
    $('signin').classList.remove('hidden');
    this.audio.pause();
    this.voiceAudio.pause();
    setTimeout(() => $('loginEmail').focus(), 50);
  }

  closeSignIn() { $('signin').classList.add('hidden'); }

  error(msg) {
    $('loginError').textContent = msg || '';
    $('loginError').classList.toggle('hidden', !msg);
  }

  // A sign-in link that failed comes back as #error=...&error_description=...
  checkLinkError() {
    const hash = new URLSearchParams(location.hash.slice(1));
    if (!hash.get('error')) return;
    history.replaceState(null, '', location.pathname);
    this.openSignIn();
    this.error(/expired|invalid/i.test(hash.get('error_description') || hash.get('error_code') || '')
      ? 'That sign-in link has expired or was already used. Enter your email for a new one.'
      : `Sign-in didn't work: ${hash.get('error_description') || hash.get('error')}`);
  }

  bindSignIn() {
    document.querySelectorAll('[data-signin]').forEach((b) => b.addEventListener('click', () => this.openSignIn()));
    $('signinClose').addEventListener('click', () => this.closeSignIn());
    $('signin').addEventListener('click', (e) => { if (e.target.id === 'signin') this.closeSignIn(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') this.closeSignIn(); });
    const busy = (btn, on, label) => { btn.disabled = on; btn.textContent = label; };

    $('emailForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      this.error();
      this.email = $('loginEmail').value.trim().toLowerCase();
      busy($('sendCodeBtn'), true, 'Sending…');
      try {
        await api.sendCode(this.email);
        $('emailForm').classList.add('hidden');
        $('codeForm').classList.remove('hidden');
        $('loginHint').textContent = `Check ${this.email}. Tap "Sign in" in the email to open Morning Brief on this device, `
          + 'or type the code here if the email has one. It can take a minute, so check spam too.';
      } catch (ex) {
        this.error(/signups? not allowed|not found|user/i.test(ex.message)
          ? "This email isn't on the invite list yet. Ask the person who invited you to add it."
          : /rate|security purposes|seconds/i.test(ex.message)
            ? 'Too many sign-in emails just now. Wait a minute and try again.' : ex.message);
      } finally {
        busy($('sendCodeBtn'), false, 'Email me a sign-in link');
      }
    });

    $('codeForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      this.error();
      const code = $('loginCode').value.trim();
      if (!code) { this.error('Tap the link in the email, or type the code if it has one.'); return; }
      busy($('verifyBtn'), true, 'Signing in…');
      try {
        await api.verifyCode(this.email, code);
        this.closeSignIn();
        await this.onSignedIn();
      } catch (ex) {
        this.error(/expired|invalid/i.test(ex.message) ? 'That code is wrong or has expired. Request a new one.' : ex.message);
      } finally {
        busy($('verifyBtn'), false, 'Sign in with code');
      }
    });

    $('changeEmail').addEventListener('click', () => {
      this.error();
      $('codeForm').classList.add('hidden');
      $('emailForm').classList.remove('hidden');
      $('loginHint').textContent = "Enter the email you were invited with. We'll email you a sign-in link.";
    });
  }

  stop() {
    this.audio.pause();
    this.voiceAudio.pause();
  }
}
