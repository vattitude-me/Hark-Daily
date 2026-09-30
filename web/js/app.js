// Morning Brief: main UI.
import { api, fmtTime, h, icon, store, timeAgo, toast } from './api.js';
import { Player } from './player.js';
import { SettingsSheet, SourcesSheet } from './sheets.js';

const SECTIONS = {
  canada: { title: 'Canada', emoji: '🇨🇦' },
  tech: { title: 'AI & Tech', emoji: '🤖' },
  custom: { title: 'My Sources', emoji: '⭐' },
};

const state = {
  briefing: null,
  tab: store.get('tab', 'all'),
  view: store.get('view', 'grid'),
  saved: store.get('saved', []),
  status: null,
  polling: null,
};

const $ = (id) => document.getElementById(id);
const player = new Player();
const sources = new SourcesSheet();
const settings = new SettingsSheet({ onBuild: () => build() });

/* ------------------------------------------------------------------ header */
function greeting() {
  const hr = new Date().getHours();
  return hr < 5 ? 'Up early' : hr < 12 ? 'Good morning' : hr < 17 ? 'Good afternoon' : 'Good evening';
}

function syncThemeIcon() {
  $('themeToggle').querySelector('use').setAttribute('href', currentTheme() === 'dark' ? '#i-sun' : '#i-moon');
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('mb-theme', theme); } catch { /* ignore */ }
  syncThemeIcon();
}

function currentTheme() {
  return document.documentElement.dataset.theme
    || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}

/* -------------------------------------------------------------------- hero */
function renderHero() {
  const b = state.briefing;
  $('greeting').textContent = greeting();
  $('todayLabel').textContent = new Date().toLocaleDateString('en-CA', { weekday: 'long', month: 'long', day: 'numeric' });
  const hasBriefing = !!b;
  $('player').classList.toggle('hidden', !hasBriefing);
  $('builder').classList.toggle('hidden', hasBriefing && !state.status?.running);

  if (!hasBriefing) {
    $('heroTitle').textContent = 'Your news, read aloud every morning';
    $('heroMeta').textContent = 'Top stories from across Canada plus the latest in AI & tech, in about five minutes.';
    $('weatherChip').classList.add('hidden');
    return;
  }
  const today = new Date().toLocaleDateString('en-CA');
  const isToday = b.date === today;
  $('heroTitle').textContent = isToday ? "Today's briefing" : b.title;
  const mins = Math.max(1, Math.round(b.duration / 60));
  $('heroMeta').textContent = `${mins} min · ${b.stories.length} stories · Voice: ${b.voice?.name || 'Default'}${isToday ? '' : ' · from the archive'}`;

  const w = b.weather;
  const chip = $('weatherChip');
  if (w && isToday) {
    chip.replaceChildren(
      h('span', { class: 'temp' }, `${w.now}°`),
      h('span', {}, h('small', {}, `${w.city} · H ${w.high}° L ${w.low}°`), h('small', {}, w.conditions)),
    );
    chip.classList.remove('hidden');
  } else chip.classList.add('hidden');
}

/* -------------------------------------------------------------------- tabs */
function renderTabs() {
  const b = state.briefing;
  const counts = { all: b?.stories.length || 0, saved: state.saved.length };
  (b?.sections || []).forEach((s) => { counts[s.key] = s.count; });
  const tabs = [
    ['all', 'All', ''],
    ...(b?.sections || []).map((s) => [s.key, s.title, SECTIONS[s.key]?.emoji || '']),
    ['saved', 'Saved', '🔖'],
  ];
  if (!tabs.some(([k]) => k === state.tab)) state.tab = 'all';
  $('tabs').replaceChildren(...tabs.map(([key, label, emoji]) => h('button', {
    class: 'tab', role: 'tab', 'aria-selected': String(state.tab === key),
    onclick: () => { state.tab = key; store.set('tab', key); renderTabs(); renderCards(); },
  }, emoji ? h('span', { 'aria-hidden': 'true' }, emoji) : null, label, h('span', { class: 'count' }, counts[key] ?? 0))));
}

/* ------------------------------------------------------------------- cards */
function isSaved(id) { return state.saved.some((s) => s.id === id); }

function toggleSave(story, btn) {
  if (isSaved(story.id)) state.saved = state.saved.filter((s) => s.id !== story.id);
  else state.saved = [{ ...story, savedFrom: state.briefing?.date }, ...state.saved].slice(0, 100);
  store.set('saved', state.saved);
  const on = isSaved(story.id);
  btn.classList.toggle('saved', on);
  btn.setAttribute('aria-pressed', String(on));
  btn.querySelector('use').setAttribute('href', on ? '#i-bookmark-fill' : '#i-bookmark');
  toast(on ? 'Saved for later' : 'Removed from saved');
  renderTabs();
  if (state.tab === 'saved') renderCards();
}

async function share(story) {
  const data = { title: story.headline, text: story.summary, url: story.url };
  try {
    if (navigator.share) await navigator.share(data);
    else { await navigator.clipboard.writeText(`${story.headline}\n${story.url}`); toast('Link copied'); }
  } catch { /* cancelled */ }
}

function card(story, index) {
  const sec = SECTIONS[story.section] || SECTIONS.custom;
  const inBriefing = state.briefing?.stories.some((s) => s.id === story.id) && state.tab !== 'saved';
  const media = story.image
    ? h('div', { class: 'card-media' }, h('img', {
      src: story.image, alt: '', loading: index < 3 ? 'eager' : 'lazy', decoding: 'async', referrerpolicy: 'no-referrer',
      onerror: (e) => { const m = e.target.parentElement; m.classList.add('placeholder'); m.dataset.section = story.section; e.target.replaceWith(h('span', {}, sec.emoji)); },
    }))
    : h('div', { class: 'card-media placeholder', dataset: { section: story.section } }, h('span', { 'aria-hidden': 'true' }, sec.emoji));
  media.append(h('span', { class: 'chip', dataset: { section: story.section } }, sec.title));

  const saveBtn = h('button', {
    class: `icon-btn${isSaved(story.id) ? ' saved' : ''}`, 'aria-label': 'Save for later', 'aria-pressed': String(isSaved(story.id)), title: 'Save',
  }, icon(isSaved(story.id) ? 'bookmark-fill' : 'bookmark'));
  saveBtn.addEventListener('click', () => toggleSave(story, saveBtn));

  const also = story.also?.length
    ? h('span', { class: 'dot' }, h('span', { class: 'also', title: `Also covered by ${story.also.join(', ')}` }, `+${story.also.length} more`))
    : null;

  return h('article', { class: 'card', id: `story-${story.id}`, dataset: { id: story.id }, style: `animation-delay:${Math.min(index, 8) * 40}ms` },
    media,
    h('div', { class: 'card-body' },
      h('div', { class: 'meta' }, h('b', {}, story.source), story.published ? h('span', { class: 'dot' }, timeAgo(story.published)) : null, also),
      h('h3', {}, story.headline),
      h('p', { class: 'summary' }, story.summary),
      h('div', { class: 'card-actions' },
        inBriefing ? h('button', { class: 'pill listen', onclick: () => player.playChapter(story.id), 'aria-label': `Listen to: ${story.headline}` },
          icon('play'), h('span', { class: 'eq', 'aria-hidden': 'true' }, h('i'), h('i'), h('i')), 'Listen',
          h('span', { class: 'dur' }, fmtTime(story.end - story.start))) : null,
        h('a', { class: 'pill', href: story.url, target: '_blank', rel: 'noopener noreferrer' }, 'Read', icon('external')),
        h('span', { class: 'spacer' }),
        h('button', { class: 'icon-btn', 'aria-label': 'Share', title: 'Share', onclick: () => share(story) }, icon('share')),
        saveBtn)));
}

function visibleStories() {
  if (state.tab === 'saved') return state.saved;
  const all = state.briefing?.stories || [];
  return state.tab === 'all' ? all : all.filter((s) => s.section === state.tab);
}

function renderCards() {
  const wrap = $('cards');
  wrap.classList.toggle('swipe', state.view === 'swipe');
  document.querySelectorAll('.view-toggle [data-view]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.view === state.view)));
  const stories = visibleStories();
  if (!stories.length) {
    const msg = state.tab === 'saved'
      ? ['Nothing saved yet', 'Tap the bookmark on any card to keep it here.']
      : state.briefing ? ['No stories here today', 'Try another section.'] : ['No briefing yet', 'Build your first briefing above. It takes a minute or two.'];
    wrap.replaceChildren(h('div', { class: 'empty' }, h('h3', {}, msg[0]), h('p', {}, msg[1])));
    $('swipeDots').classList.add('hidden');
    return;
  }
  wrap.replaceChildren(...stories.map(card));
  highlight(player.current);
  renderDots();
}

function renderDots() {
  const dots = $('swipeDots');
  const n = $('cards').children.length;
  dots.classList.toggle('hidden', state.view !== 'swipe' || n < 2);
  if (state.view !== 'swipe') return;
  dots.replaceChildren(...Array.from({ length: n }, (_, i) => h('i', { class: i === 0 ? 'on' : '' })));
}

function highlight(id) {
  document.querySelectorAll('.card.is-playing').forEach((c) => c.classList.remove('is-playing', 'audio-on'));
  if (!id) return;
  const el = document.getElementById(`story-${id}`);
  if (!el) return;
  el.classList.add('is-playing');
  el.classList.toggle('audio-on', player.isPlaying);
  if (state.view === 'swipe' && player.isPlaying) el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
}

/* ----------------------------------------------------------------- builder */
function showProgress(status) {
  const running = status?.running;
  const label = status?.step || 'Starting…';
  const pct = `${Math.round((status?.progress || 0) * 100)}%`;
  $('buildProgress').classList.toggle('hidden', !running);
  $('buildBtn').classList.toggle('hidden', !!running);
  $('buildBar').style.width = pct;
  $('buildStep').textContent = `${label}…`.replace(/……$/, '…');
  if (running) $('builderCopy').textContent = 'Hang tight. Your briefing is being prepared. This usually takes a minute or two.';
  const sp = $('settingsProgress');
  sp.classList.toggle('hidden', !running);
  sp.querySelector('.progress-bar span').style.width = pct;
  sp.querySelector('.progress-label').textContent = label;
  $('rebuildBtn').disabled = !!running;
  if (running) $('builder').classList.remove('hidden');
}

async function build() {
  try {
    await api.generate();
    toast('Building a fresh briefing…');
    poll();
  } catch (err) { toast(err.message, { error: true }); }
}

function poll() {
  clearInterval(state.polling);
  const tick = async () => {
    try {
      const status = await api.status();
      const wasRunning = state.status?.running;
      state.status = status;
      showProgress(status);
      if (!status.running) {
        clearInterval(state.polling);
        state.polling = null;
        if (status.error) toast(status.error, { error: true, ms: 7000 });
        else if (wasRunning) { toast('Your new briefing is ready ☀️'); await loadBriefing(); }
        renderHero();
      }
    } catch { /* keep polling through blips */ }
  };
  tick();
  state.polling = setInterval(tick, 1500);
}

/* ----------------------------------------------------------------- loading */
async function loadArchive(selected) {
  const { briefings } = await api.archive();
  const sel = $('archiveSelect');
  const today = new Date().toLocaleDateString('en-CA');
  sel.replaceChildren(...briefings.map((b) => {
    const label = b.date === today ? 'Today' : new Date(`${b.date}T12:00`).toLocaleDateString('en-CA', { weekday: 'short', month: 'short', day: 'numeric' });
    const opt = h('option', { value: b.date }, label);
    opt.selected = b.date === selected;
    return opt;
  }));
}

async function loadBriefing(day) {
  const res = day ? await api.briefing(day) : await api.latest();
  state.briefing = res.briefing;
  if (state.briefing) player.load(state.briefing);
  const writer = state.briefing?.writer === 'claude' ? 'Written by Claude' : 'Summarized on your server';
  $('footnote').textContent = state.briefing
    ? `${writer} · voiced by ${state.briefing.voice?.name || 'Kokoro'} · built ${timeAgo(state.briefing.generated_at)}`
    : '';
  renderHero();
  renderTabs();
  renderCards();
  await loadArchive(state.briefing?.date);
}

/* ------------------------------------------------------------------ events */
function bindEvents() {
  $('buildBtn').addEventListener('click', build);
  $('openSources').addEventListener('click', () => sources.open().catch((e) => toast(e.message, { error: true })));
  $('openSettings').addEventListener('click', () => settings.open(state.status).catch((e) => toast(e.message, { error: true })));
  $('themeToggle').addEventListener('click', () => setTheme(currentTheme() === 'dark' ? 'light' : 'dark'));
  $('archiveSelect').addEventListener('change', (e) => loadBriefing(e.target.value));
  $('settingsSheet').addEventListener('close', async () => {
    try { state.status = await api.status(); } catch { /* ignore */ }
  });

  document.querySelectorAll('.view-toggle [data-view]').forEach((b) => b.addEventListener('click', () => {
    state.view = b.dataset.view;
    store.set('view', state.view);
    renderCards();
  }));

  $('cards').addEventListener('scroll', () => {
    if (state.view !== 'swipe') return;
    const wrap = $('cards');
    const idx = Math.round(wrap.scrollLeft / (wrap.firstElementChild?.offsetWidth + 16 || 1));
    $('swipeDots').querySelectorAll('i').forEach((d, i) => d.classList.toggle('on', i === idx));
  }, { passive: true });

  player.addEventListener('chapter', (e) => highlight(e.detail.id));
  player.addEventListener('state', () => highlight(player.current));

  document.addEventListener('keydown', (e) => {
    if (e.target.closest('input, textarea, select, dialog[open]') || e.metaKey || e.ctrlKey) return;
    if (e.key === ' ' || e.key === 'k') { e.preventDefault(); player.toggle(); }
    else if (e.key === 'j' || e.key === 'ArrowDown' && e.shiftKey) player.nextChapter();
    else if (e.key === 'ArrowRight' && state.view === 'swipe') $('cards').scrollBy({ left: 300, behavior: 'smooth' });
    else if (e.key === 'ArrowLeft' && state.view === 'swipe') $('cards').scrollBy({ left: -300, behavior: 'smooth' });
    else if (e.key === 'l') player.skip(30);
    else if (e.key === 'h') player.skip(-15);
  });

  document.addEventListener('visibilitychange', async () => {
    // Coming back to the tab in the morning? Pick up the new briefing.
    if (document.visibilityState !== 'visible' || player.isPlaying) return;
    try {
      const { briefing } = await api.latest();
      if (briefing && briefing.generated_at !== state.briefing?.generated_at && $('archiveSelect').selectedIndex <= 0) {
        await loadBriefing();
      }
    } catch { /* offline */ }
  });
}

/* -------------------------------------------------------------------- boot */
async function init() {
  syncThemeIcon(); // follows the OS until the user picks a theme
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', syncThemeIcon);
  bindEvents();
  renderHero();
  $('cards').replaceChildren(...Array.from({ length: 3 }, () => h('div', { class: 'skeleton' })));
  try {
    const [status] = await Promise.all([api.status(), loadBriefing()]);
    state.status = status;
    showProgress(status);
    renderHero();
    if (status.running) poll();
  } catch (err) {
    toast(`Couldn't reach the server: ${err.message}`, { error: true, ms: 8000 });
    renderCards();
  }
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
}

init();
