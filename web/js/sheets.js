// Sources and Voice & settings sheets.
import { api, clockLabel, h, icon, timeAgo, toast } from './api.js';

const SECTION_LABEL = { canada: '🇨🇦 Canada', tech: '🤖 AI & Tech', custom: '⭐ My Sources' };

export function wireSheet(dialog) {
  dialog.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
}

/* ------------------------------------------------------------------ Sources */
export class SourcesSheet {
  constructor() {
    this.dialog = document.getElementById('sourcesSheet');
    this.list = document.getElementById('sourceList');
    this.form = document.getElementById('addSourceForm');
    this.urlInput = document.getElementById('sourceUrl');
    this.checkBtn = document.getElementById('checkSourceBtn');
    wireSheet(this.dialog);
    this.form.addEventListener('submit', (e) => { e.preventDefault(); this.check(); });
  }

  async open() {
    this.dialog.showModal();
    await this.refresh();
  }

  section() {
    return this.form.querySelector('input[name="section"]:checked').value;
  }

  async check() {
    let url = this.urlInput.value.trim();
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
    try { url = new URL(url).href; } catch {
      toast("That doesn't look like a web link.", { error: true });
      return;
    }
    this.checkBtn.disabled = true;
    this.checkBtn.textContent = 'Adding…';
    try {
      await api.addSource({ url, section: this.section() });
      toast('Added. It will be checked at the next morning build.');
      this.urlInput.value = '';
      await this.refresh();
    } catch (err) {
      toast(err.message, { error: true });
    } finally {
      this.checkBtn.disabled = false;
      this.checkBtn.textContent = 'Add link';
    }
  }

  async refresh() {
    const { sources } = await api.sources();
    const groups = { custom: [], canada: [], tech: [] };
    sources.forEach((s) => (groups[s.section] || groups.custom).push(s));
    // Your own links first, then built-ins alphabetically.
    Object.values(groups).forEach((g) => g.sort((a, b) => a.builtin - b.builtin || a.name.localeCompare(b.name)));
    this.list.replaceChildren(
      ...Object.entries(groups)
        .filter(([, items]) => items.length)
        .map(([key, items]) => h('section', { class: 'source-group' },
          h('h3', {}, SECTION_LABEL[key], h('span', { class: 'tag' }, `${items.filter((s) => s.enabled).length} on`)),
          items.map((s) => this.row(s)))),
    );
  }

  row(s) {
    const host = (() => { try { return new URL(s.url).hostname.replace(/^www\./, ''); } catch { return s.url; } })();
    const ok = s.last_status === 'ok';
    const pending = s.kind === 'auto' && !s.last_status;
    const statusText = pending ? 'Waiting for the next morning build'
      : s.last_status
        ? ok ? `${s.last_count ?? 0} ${s.last_count === 1 ? 'story' : 'stories'} · ${timeAgo(s.last_fetched_at)}` : s.last_status
        : 'Not checked yet';
    const toggle = h('input', { type: 'checkbox', 'aria-label': `Use ${s.name}` });
    toggle.checked = s.enabled;
    toggle.addEventListener('change', async () => {
      try { await api.updateSource(s, { enabled: toggle.checked }); } catch (err) {
        toggle.checked = !toggle.checked;
        toast(err.message, { error: true });
      }
    });
    const del = s.builtin ? null : h('button', {
      class: 'icon-btn', 'aria-label': `Remove ${s.name}`, title: 'Remove',
      onclick: async () => {
        if (!confirm(`Remove ${s.name}?`)) return;
        try { await api.deleteSource(s.id); await this.refresh(); } catch (err) { toast(err.message, { error: true }); }
      },
    }, icon('trash'));
    return h('div', { class: 'source-row' },
      h('label', { class: 'switch' }, toggle, h('span')),
      h('div', { class: 'source-info' },
        h('span', { class: 'source-name', title: s.name }, s.name),
        h('span', { class: 'source-sub', title: statusText },
          h('span', { class: `status-dot ${s.last_status ? (ok ? 'ok' : 'err') : ''}` }),
          s.builtin ? null : h('span', { class: 'tag' }, s.kind === 'article' ? (s.consumed_at ? 'used' : 'queued') : s.kind === 'auto' ? 'new' : s.kind),
          `${host} · ${statusText}`)),
      del);
  }
}

/* ----------------------------------------------------------------- Settings */
export class SettingsSheet {
  constructor({ onBuild }) {
    this.dialog = document.getElementById('settingsSheet');
    this.onBuild = onBuild;
    this.previewAudio = new Audio();
    wireSheet(this.dialog);
    this.dialog.addEventListener('close', () => this.previewAudio.pause());
    document.getElementById('saveSettings').addEventListener('click', () => this.save());
    document.getElementById('rebuildBtn').addEventListener('click', () => this.onBuild());
    document.getElementById('pushOn').addEventListener('change', (e) => this.togglePush(e.target));
    document.getElementById('pushTest').addEventListener('click', (e) => this.testPush(e.currentTarget));
    document.getElementById('signOutBtn').addEventListener('click', async () => { await api.signOut(); location.reload(); });
    const range = document.getElementById('speedRange');
    range.addEventListener('input', () => { document.getElementById('speedOut').textContent = `${Number(range.value).toFixed(2).replace(/0$/, '')}×`; });
  }

  async open(status, profile) {
    this.dialog.showModal();
    this.status = status || {};
    const { settings } = await api.settings();
    this.settings = settings;
    this.renderVoices(this.status.voices || [], settings.voice);
    const range = document.getElementById('speedRange');
    range.value = settings.speed;
    range.dispatchEvent(new Event('input'));
    document.getElementById('nameInput').value = settings.name || '';
    document.getElementById('dailyOn').checked = settings.daily !== false;
    document.getElementById('weatherOn').checked = settings.weather;
    document.getElementById('cityInput').value = settings.city;
    document.getElementById('latInput').value = settings.latitude;
    document.getElementById('lonInput').value = settings.longitude;
    document.getElementById('accountEmail').textContent = profile?.email || '';
    document.getElementById('rebuildGroup').classList.toggle('hidden', !profile?.is_admin);
    this.renderSteppers(settings.stories);
    this.showStatus(this.status);
    this.refreshPush();
  }

  async refreshPush() {
    const box = document.getElementById('pushOn');
    const hint = document.getElementById('pushHint');
    const supported = 'serviceWorker' in navigator && 'PushManager' in window && window.isSecureContext;
    box.disabled = !supported;
    if (!supported) {
      hint.textContent = 'Notifications need HTTPS and an installed app (on iPhone: Add to Home Screen first).';
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    box.checked = !!(await reg.pushManager.getSubscription()) && Notification.permission === 'granted';
    hint.textContent = Notification.permission === 'denied' ? 'Notifications are blocked in this browser\'s site settings.' : '';
  }

  async togglePush(box) {
    const hint = document.getElementById('pushHint');
    try {
      const reg = await navigator.serviceWorker.ready;
      const existing = await reg.pushManager.getSubscription();
      if (!box.checked) {
        if (existing) { await api.pushUnsubscribe(existing.toJSON()); await existing.unsubscribe(); }
        return;
      }
      if (await Notification.requestPermission() !== 'granted') throw new Error('Permission was not granted.');
      const public_key = this.status?.vapid_public_key;
      if (!public_key) throw new Error("The server hasn't published its notification key yet. Try again later.");
      const pad = '='.repeat((4 - (public_key.length % 4)) % 4);
      const raw = atob((public_key + pad).replace(/-/g, '+').replace(/_/g, '/'));
      const key = Uint8Array.from(raw, (c) => c.charCodeAt(0));
      const sub = existing || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
      await api.pushSubscribe(sub.toJSON());
      hint.textContent = 'You will be notified each morning when the briefing is ready.';
    } catch (err) {
      box.checked = false;
      hint.textContent = err.message;
    }
  }

  async testPush(btn) {
    const hint = document.getElementById('pushHint');
    btn.disabled = true;
    hint.textContent = 'Asking the server to send a test…';
    try {
      const r = await api.pushTest();
      hint.textContent = r.status === 'done' ? `${r.message}.` : r.message;
    } catch (err) {
      hint.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  }

  showStatus(status) {
    const at = clockLabel(status.batch_time);
    const keep = status.keep_days || 2;
    document.getElementById('nextRun').textContent = at
      ? `Briefings are built every day at ${at} (${(status.timezone || 'America/Toronto').split('/').pop().replace('_', ' ')} time).`
      : '';
    const max = status.limits?.max_custom_sources || 15;
    const items = [
      `New links you add are checked and used at the next morning build${at ? ` (${at})` : ''}.`,
      `Only ${keep === 2 ? "today's and yesterday's" : `the last ${keep} days'`} briefings are kept. Use the Read links on each card for the full stories.`,
      'Summaries are written by a free AI service with a daily limit. If it runs out, the built-in summarizer takes over (shorter, plainer summaries) and a note appears on your briefing.',
      `Up to ${max} of your own links are used each day. A red dot in Sources means a link couldn't be read.`,
      'If something goes wrong with a build, the admin is notified automatically.',
    ];
    document.getElementById('limitsList').replaceChildren(...items.map((t) => h('li', {}, t)));
  }

  renderVoices(voices, selected) {
    const grid = document.getElementById('voiceGrid');
    const byEngine = { kokoro: 'Kokoro · natural, recorded on our server', edge: 'Microsoft neural · includes Canadian voices' };
    const nodes = [];
    for (const [engine, label] of Object.entries(byEngine)) {
      const list = voices.filter((v) => v.engine === engine);
      if (!list.length) continue;
      nodes.push(h('div', { class: 'voice-section-label' }, label));
      for (const v of list) {
        const radio = h('input', { type: 'radio', name: 'voice', value: v.id });
        radio.checked = v.id === selected;
        const btn = h('button', { type: 'button', class: 'preview-btn', 'aria-label': `Hear ${v.name}` }, icon('play'));
        btn.addEventListener('click', (e) => { e.preventDefault(); this.preview(v, btn); });
        nodes.push(h('label', { class: 'voice-card', title: v.note || '' },
          radio,
          v.recommended ? h('span', { class: 'badge' }, 'Recommended') : null,
          h('span', { class: 'avatar' }, v.name[0]),
          h('span', {},
            h('span', { class: 'v-name' }, v.name),
            h('span', { class: 'v-meta' }, `${v.accent} · ${v.gender}`),
            h('span', { class: 'v-desc' }, v.description)),
          btn));
      }
    }
    grid.replaceChildren(...nodes);
  }

  preview(voice, btn) {
    const src = voice.preview_url;
    const a = this.previewAudio;
    if (a.dataset.src === src && !a.paused) { a.pause(); return; }
    document.querySelectorAll('.preview-btn.loading').forEach((b) => b.classList.remove('loading'));
    btn.classList.add('loading');
    a.dataset.src = src;
    a.src = src;
    a.onplaying = () => btn.classList.remove('loading');
    a.onerror = () => { btn.classList.remove('loading'); toast("Couldn't load that voice sample.", { error: true }); };
    a.playbackRate = Number(document.getElementById('speedRange').value) || 1;
    a.play().catch(() => btn.classList.remove('loading'));
  }

  renderSteppers(stories) {
    const labels = { canada: '🇨🇦 Canada', tech: '🤖 AI & Tech', custom: '⭐ My Sources' };
    this.stories = { ...stories };
    document.getElementById('storySteppers').replaceChildren(
      ...Object.entries(labels).map(([key, label]) => {
        const out = h('output', {}, this.stories[key]);
        const step = (d) => { this.stories[key] = Math.max(0, Math.min(10, this.stories[key] + d)); out.textContent = this.stories[key]; };
        return h('div', { class: 'stepper' }, h('span', {}, label),
          h('div', { class: 'stepper-ctrl' },
            h('button', { type: 'button', 'aria-label': `Fewer ${label} stories`, onclick: () => step(-1) }, '−'),
            out,
            h('button', { type: 'button', 'aria-label': `More ${label} stories`, onclick: () => step(1) }, '+')));
      }),
    );
  }

  async save() {
    const voice = this.dialog.querySelector('input[name="voice"]:checked')?.value;
    const lat = parseFloat(document.getElementById('latInput').value);
    const lon = parseFloat(document.getElementById('lonInput').value);
    const body = {
      voice,
      speed: Number(document.getElementById('speedRange').value),
      name: document.getElementById('nameInput').value.trim().slice(0, 40),
      daily: document.getElementById('dailyOn').checked,
      weather: document.getElementById('weatherOn').checked,
      city: document.getElementById('cityInput').value.trim() || 'Toronto',
      stories: this.stories,
    };
    if (Number.isFinite(lat)) body.latitude = lat;
    if (Number.isFinite(lon)) body.longitude = lon;
    try {
      const res = await api.saveSettings(body);
      const voiceChanged = voice !== this.settings.voice || body.speed !== this.settings.speed;
      toast(voiceChanged ? 'Saved. Tomorrow\'s briefing will use the new voice.' : 'Saved. Changes apply from the next briefing.');
      this.dialog.close();
      return res;
    } catch (err) {
      toast(err.message, { error: true });
    }
  }
}
