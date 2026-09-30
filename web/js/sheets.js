// Sources and Voice & settings sheets.
import { api, h, icon, timeAgo, toast } from './api.js';

const KIND_LABEL = {
  feed: 'RSS feed · checked every morning',
  page: 'Web page · headlines scraped every morning',
  article: 'Single article · goes into your next briefing',
};
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
    this.preview = document.getElementById('sourcePreview');
    this.checkBtn = document.getElementById('checkSourceBtn');
    wireSheet(this.dialog);
    this.form.addEventListener('submit', (e) => { e.preventDefault(); this.check(); });
    this.urlInput.addEventListener('input', () => this.preview.classList.add('hidden'));
  }

  async open() {
    this.dialog.showModal();
    await this.refresh();
  }

  section() {
    return this.form.querySelector('input[name="section"]:checked').value;
  }

  async check() {
    const url = this.urlInput.value.trim();
    if (!url) return;
    this.checkBtn.disabled = true;
    this.checkBtn.textContent = 'Checking…';
    this.preview.classList.remove('hidden');
    this.preview.replaceChildren(h('p', { class: 'hint' }, 'Looking for news on that page…'));
    try {
      const d = await api.detectSource(url);
      const nameInput = h('input', { type: 'text', class: 'text-input', value: d.name, 'aria-label': 'Source name', maxlength: 120 });
      const addBtn = h('button', { type: 'button', class: 'btn btn-primary' }, icon('plus'), d.exists ? 'Already added' : 'Add source');
      if (d.exists) addBtn.disabled = true;
      addBtn.addEventListener('click', () => this.add(url, nameInput.value.trim(), addBtn));
      this.preview.replaceChildren(
        h('span', { class: 'kind' }, KIND_LABEL[d.kind] || d.kind),
        nameInput,
        d.sample.length ? h('ul', {}, d.sample.map((t) => h('li', {}, t))) : null,
        addBtn,
      );
    } catch (err) {
      this.preview.replaceChildren(h('p', { class: 'error' }, err.message));
    } finally {
      this.checkBtn.disabled = false;
      this.checkBtn.textContent = 'Check link';
    }
  }

  async add(url, name, btn) {
    btn.disabled = true;
    btn.textContent = 'Adding…';
    try {
      const { source } = await api.addSource({ url, section: this.section(), name: name || null });
      toast(source.kind === 'article' ? 'Saved. It will be in your next briefing.' : `Added ${source.name}`);
      this.urlInput.value = '';
      this.preview.classList.add('hidden');
      await this.refresh();
    } catch (err) {
      toast(err.message, { error: true });
      btn.disabled = false;
      btn.textContent = 'Add source';
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
    const statusText = s.last_status
      ? ok ? `${s.last_count ?? 0} ${s.last_count === 1 ? 'story' : 'stories'} · ${timeAgo(s.last_fetched_at)}` : s.last_status
      : 'Not checked yet';
    const toggle = h('input', { type: 'checkbox', 'aria-label': `Use ${s.name}` });
    toggle.checked = s.enabled;
    toggle.addEventListener('change', async () => {
      try { await api.updateSource(s.id, { enabled: toggle.checked }); } catch (err) {
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
          s.builtin ? null : h('span', { class: 'tag' }, s.kind === 'article' ? (s.consumed_at ? 'used' : 'queued') : s.kind),
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
    const range = document.getElementById('speedRange');
    range.addEventListener('input', () => { document.getElementById('speedOut').textContent = `${Number(range.value).toFixed(2).replace(/0$/, '')}×`; });
  }

  async open(status) {
    this.dialog.showModal();
    const [{ settings }, { voices }] = await Promise.all([api.settings(), api.voices()]);
    this.settings = settings;
    this.renderVoices(voices, settings.voice);
    const range = document.getElementById('speedRange');
    range.value = settings.speed;
    range.dispatchEvent(new Event('input'));
    document.getElementById('autoGenerate').checked = settings.auto_generate;
    document.getElementById('briefingTime').value = settings.briefing_time;
    document.getElementById('weatherOn').checked = settings.weather;
    document.getElementById('cityInput').value = settings.city;
    document.getElementById('latInput').value = settings.latitude;
    document.getElementById('lonInput').value = settings.longitude;
    this.renderSteppers(settings.stories);
    this.showStatus(status);
  }

  showStatus(status) {
    if (!status) return;
    document.getElementById('writerInfo').textContent = status.writer === 'claude'
      ? 'Summaries and the script are written by Claude, then read by your chosen voice.'
      : 'Summaries come from the built-in summarizer. Add an ANTHROPIC_API_KEY for radio-quality scripts written by Claude.';
    const next = status.next_run ? new Date(status.next_run) : null;
    document.getElementById('nextRun').textContent = next
      ? `Next briefing: ${next.toLocaleString('en-CA', { weekday: 'long', hour: 'numeric', minute: '2-digit' })}`
      : 'Automatic briefings are off.';
  }

  renderVoices(voices, selected) {
    const grid = document.getElementById('voiceGrid');
    const byEngine = { kokoro: 'Kokoro · runs on your server, free & private', edge: 'Microsoft neural · online, includes Canadian voices' };
    const nodes = [];
    for (const [engine, label] of Object.entries(byEngine)) {
      const list = voices.filter((v) => v.engine === engine);
      if (!list.length) continue;
      nodes.push(h('div', { class: 'voice-section-label' }, label));
      for (const v of list) {
        const radio = h('input', { type: 'radio', name: 'voice', value: v.id });
        radio.checked = v.id === selected;
        const btn = h('button', { type: 'button', class: 'preview-btn', 'aria-label': `Hear ${v.name}` }, icon('play'));
        btn.addEventListener('click', (e) => { e.preventDefault(); this.preview(v.id, btn); });
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

  preview(voiceId, btn) {
    const speed = Number(document.getElementById('speedRange').value);
    const src = api.previewUrl(voiceId, speed);
    const a = this.previewAudio;
    if (a.dataset.src === src && !a.paused) { a.pause(); return; }
    document.querySelectorAll('.preview-btn.loading').forEach((b) => b.classList.remove('loading'));
    btn.classList.add('loading');
    a.dataset.src = src;
    a.src = src;
    a.onplaying = () => btn.classList.remove('loading');
    a.onerror = () => { btn.classList.remove('loading'); toast("Couldn't load that voice sample.", { error: true }); };
    a.play().catch(() => btn.classList.remove('loading'));
  }

  renderSteppers(stories) {
    const labels = { canada: '🇨🇦 Canada', tech: '🤖 AI & Tech', custom: '⭐ My Sources' };
    this.stories = { ...stories };
    document.getElementById('storySteppers').replaceChildren(
      ...Object.entries(labels).map(([key, label]) => {
        const out = h('output', {}, this.stories[key]);
        const step = (d) => { this.stories[key] = Math.max(0, Math.min(12, this.stories[key] + d)); out.textContent = this.stories[key]; };
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
      auto_generate: document.getElementById('autoGenerate').checked,
      briefing_time: document.getElementById('briefingTime').value || '06:30',
      weather: document.getElementById('weatherOn').checked,
      city: document.getElementById('cityInput').value.trim() || 'Toronto',
      stories: this.stories,
    };
    if (Number.isFinite(lat)) body.latitude = lat;
    if (Number.isFinite(lon)) body.longitude = lon;
    try {
      const res = await api.saveSettings(body);
      const voiceChanged = voice !== this.settings.voice || body.speed !== this.settings.speed;
      toast(voiceChanged ? 'Saved. Your next briefing will use the new voice.' : 'Settings saved');
      this.dialog.close();
      return res;
    } catch (err) {
      toast(err.message, { error: true });
    }
  }
}
