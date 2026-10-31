import { api, fmtTime, h, icon, isAdmin, recordError, sb, store, timeAgo, toast, VOICES, voiceFor, SECTIONS, DEFAULT_VOICE_ID, EDITIONS, defaultEdition, detectEditionFromIp } from './api.js';
import { Player, posKeyFor } from './player.js';
import { Landing } from './landing.js';
import { WelcomeSheet, DeleteAccountSheet, enablePush, installMode, onInstallChange, promptInstall, pushSupported, requestNotificationPermission, wireSheet } from './sheets.js';
import { SourcesPage } from './pages/sources.js';
import { SettingsPage } from './pages/settings.js';
import { AdminPage } from './pages/admin.js';
import { buildBriefing as buildPackBriefing, READY_KEY, storyKey, titlesMatch } from './storypack.js';
import { applyPhotoMode } from './design.js';

import { FEATURES } from '../config.js';

// Native Android / Capacitor shell safe-area and status bar initialization
if (window.HarkNative || window.Capacitor?.isNativePlatform?.()) {
  document.documentElement.classList.add('native-shell');
  try {
    const top = window.HarkNative?.getSafeAreaTop?.();
    if (typeof top === 'number' && top > 0) {
      document.documentElement.style.setProperty('--safe-area-inset-top', `${top}px`);
    }
    const bottom = window.HarkNative?.getSafeAreaBottom?.();
    if (typeof bottom === 'number' && bottom > 0) {
      document.documentElement.style.setProperty('--safe-area-inset-bottom', `${bottom}px`);
    }
    const curTh = document.documentElement.dataset.theme || localStorage.getItem('mb-theme') || 'light';
    window.HarkNative?.setStatusBarTheme?.(curTh);
  } catch (e) {
    console.warn('[app] error reading native safe areas:', e);
  }
}

const state = {
  briefing: null,
  briefingLoading: true,
  profile: null,
  status: null,
  archiveDates: [],
  reported: new Set(store.get('reported', [])),
  mode: 'podcast',
  edition: store.get('edition', defaultEdition()),
  packContext: null,
};

const $ = (id) => document.getElementById(id);

export function trackEvent(name, params = {}) {
  try {
    if (typeof window !== 'undefined' && typeof window.gtag === 'function') {
      window.gtag('event', name, params);
    }
  } catch { /* ignore analytics errors */ }
}
window.trackEvent = trackEvent;

const player = new Player();
window.player = player;
window.state = state;
window.switchTab = switchTab;
let sourcesPage = null;
let settingsPage = null;
let adminPage = null;
let currentTab = 'today';
const welcome = new WelcomeSheet({
  onDone: async () => { try { state.profile = await api.profile(); } catch { /* keep the old one */ } syncAdminTab(); renderHeader(); },
});

/** The admin tab shows for the admin account. The worker and the database check it again. */
function syncAdminTab() {
  const tab = $('adminTab');
  if (tab) tab.classList.toggle('hidden', !isAdmin(state.profile));
}
window.syncAdminTab = syncAdminTab;

/* ------------------------------------------------------------------ header */
function syncInstallBtn() {
  $('installBtn')?.classList.toggle('hidden', !installMode());
}

async function install() {
  if (installMode() === 'ios') { $('installSheet').showModal(); return; }
  if (await promptInstall()) toast('Installed. Next time, open Hark Daily from your home screen.');
}

function syncThemeIcon() {
  $('themeToggle')?.querySelector('use')?.setAttribute('href', currentTheme() === 'dark' ? '#i-sun' : '#i-moon');
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('mb-theme', theme); } catch { /* ignore */ }
  try { window.HarkNative?.setStatusBarTheme?.(theme); } catch { /* ignore */ }
  syncThemeIcon();
}

function currentTheme() {
  return document.documentElement.dataset.theme || 'light';
}

const WORDS = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];
/** "12 stories, six minutes. Light drizzle, high 21°." */
function summaryLine(b) {
  const n = b.stories.length;
  const minutes = Math.max(1, Math.round(b.duration / 60));
  const m = WORDS[minutes - 1] || String(minutes);
  let line = `${n === 1 ? '1 story' : `${n} stories`}, ${m} minute${minutes === 1 ? '' : 's'}.`;
  if (b.weather && b.weather.conditions) line += ` ${b.weather.conditions[0].toUpperCase()}${b.weather.conditions.slice(1)}, high ${b.weather.high}°.`;
  return line;
}

export function formatFreshnessDate(dateStr) {
  let d;
  if (dateStr && /^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    const [y, m, day] = dateStr.split('-').map(Number);
    d = new Date(y, m - 1, day);
  } else {
    d = new Date();
  }
  const wd = d.toLocaleDateString('en-US', { weekday: 'short' });
  const mon = d.toLocaleDateString('en-US', { month: 'short' });
  const num = d.getDate();
  const sfx = (num % 10 === 1 && num !== 11) ? 'st'
            : (num % 10 === 2 && num !== 12) ? 'nd'
            : (num % 10 === 3 && num !== 13) ? 'rd'
            : 'th';
  return `${wd} ${mon} ${num}${sfx}`;
}

function renderHeader() {
  const now = new Date();
  const wd = now.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
  const mon = now.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();

  // Time-based greeting with user's name
  const hr = now.getHours();
  const baseGreeting = hr < 12 ? 'Good morning' : hr < 17 ? 'Good afternoon' : 'Good evening';
  const name = state.profile?.settings?.name || '';
  const greetingEl = $('greeting');
  if (greetingEl) {
    greetingEl.textContent = name.trim() ? `${baseGreeting}, ${name.trim()}` : baseGreeting;
  }
  const lgGreeting = $('lgGreeting');
  if (lgGreeting) lgGreeting.textContent = baseGreeting;

  // Status text chip
  const b = state.briefing;
  const statusChip = $('statusChip');
  const statusText = $('statusText');
  if (statusText) {
    if (b) {
      const minutes = Math.max(1, Math.round((b.duration || 0) / 60));
      const w = b.weather;
      statusText.textContent = w ? `${w.city} ${w.now}° · ${b.stories.length} stories` : `${b.stories.length} stories · ${minutes}m`;
      if (statusChip) statusChip.classList.remove('hidden');
    } else {
      statusText.textContent = 'Curating';
    }
  }

  // Weather chip (safely guarded)
  const wxChip = $('wxChip');
  if (wxChip) {
    const w = b?.weather;
    wxChip.textContent = w ? `${w.city} ${w.now}°` : '';
  }

  // Active narrator chip & preview
  const isPodcast = activeMode() === 'podcast';
  const activeVoiceId = b?.voice?.id || state.profile?.settings?.voice || DEFAULT_VOICE_ID;
  const activeVoice = voiceFor(activeVoiceId);
  const nName = $('narratorName');
  if (nName) nName.textContent = isPodcast && b?.voice?.name ? b.voice.name : activeVoice.name;
  const nDesc = $('narratorDesc');
  if (nDesc) nDesc.textContent = isPodcast ? 'Podcast co-hosts' : (activeVoice.style || activeVoice.desc);
  const narrBy = $('narratedBy');
  if (narrBy) {
    if (isPodcast) {
      narrBy.textContent = `Voiced by ${b?.voice?.name || 'co-hosts'} · Daily podcast discussion`;
    } else if (b?.voice?.isFallback && b?.voice?.requested) {
      narrBy.textContent = `Narrated by ${activeVoice.name} (${voiceName(b.voice.requested)} unrecorded) · ${activeVoice.style || activeVoice.desc}`;
    } else {
      narrBy.textContent = `Narrated by ${activeVoice.name} · ${activeVoice.style || activeVoice.desc}`;
    }
  }
  const heroNarrName = $('heroNarratorName');
  if (heroNarrName) heroNarrName.textContent = b?.voice?.name || activeVoice.name;

  const heroNarrBtn = $('heroNarratorBtn');
  const narrChip = $('narratorChip');
  if (isPodcast) {
    heroNarrBtn?.classList.add('is-podcast-locked');
    heroNarrBtn?.setAttribute('aria-label', `${b?.voice?.name || 'Co-hosts'} (locked in Podcast mode)`);
    heroNarrBtn?.setAttribute('title', 'Podcast mode uses pre-selected co-hosts. Switch to Full Brief to change narrator.');
    narrChip?.classList.add('is-podcast-locked');
    narrChip?.setAttribute('title', 'Podcast mode uses pre-selected co-hosts. Switch to Full Brief to change narrator.');
  } else {
    heroNarrBtn?.classList.remove('is-podcast-locked');
    heroNarrBtn?.setAttribute('aria-label', 'Change narrator');
    heroNarrBtn?.setAttribute('title', 'Change narrator');
    narrChip?.classList.remove('is-podcast-locked');
    narrChip?.setAttribute('title', 'Change narrator');
  }

  // Avatar and Sign In controls for guest vs signed-in
  const isGuest = !state.profile;
  const topbarSignInBtn = $('topbarSignInBtn');
  if (topbarSignInBtn) {
    topbarSignInBtn.classList.toggle('hidden', !isGuest);
  }
  const avatarBtn = $('avatarBtn');
  if (avatarBtn) {
    avatarBtn.classList.toggle('hidden', isGuest);
  }
  const syncLabel = $('syncLabel');
  if (syncLabel) {
    syncLabel.textContent = isGuest ? 'Guest mode' : 'Synced';
  }

  // Move audio briefing date info to hamburger menu drawer
  const menuDate = $('menuDrawerDateText');
  if (menuDate) {
    const day = now.getDate();
    menuDate.textContent = `FRESH TODAY · ${wd} ${day} ${mon}`;
  }
  const menuMeta = $('menuDrawerMetaText');
  if (menuMeta) {
    if (b) {
      const minutes = Math.max(1, Math.round((b.duration || 0) / 60));
      menuMeta.textContent = `${b.stories?.length || 0} stories · ${minutes}m · Updated at sunrise`;
    } else {
      menuMeta.textContent = 'Voiced at sunrise · Updated daily';
    }
  }
  const menuTodayVal = $('menuTodayVal');
  if (menuTodayVal && b) {
    const minutes = Math.max(1, Math.round((b.duration || 0) / 60));
    menuTodayVal.textContent = `${b.stories?.length || 0} stories · ${minutes}m`;
  }

  // Avatar initial
  const avInitial = $('avatarInitial');
  if (avInitial) {
    const raw = name || state.profile?.email || '';
    if (raw.trim()) avInitial.textContent = raw.trim()[0].toUpperCase();
  }

  const bTitle = $('briefTitle');
  if (bTitle) {
    bTitle.textContent = isPodcast ? 'Daily Podcast Newsreader' : 'Daily Spoken Newsreader';
  }

  const sub = $('screenSubtitle');
  if (sub) {
    if (isPodcast) {
      const storyCount = b?.stories?.length || 35;
      const mins = Math.max(1, Math.round((b?.duration || 840) / 60));
      sub.textContent = `${storyCount} stories, ${mins} min · Voiced by Matthew & Kelly · Listen anywhere`;
    } else {
      const baseSummary = b ? summaryLine(b) : 'Your news, read aloud each morning.';
      sub.textContent = b ? `${baseSummary} · Read by ${activeVoice.name}` : baseSummary;
    }
  }

  const tag = $('freshnessTag');
  if (tag) {
    const bDate = b?.date;
    const formatted = formatFreshnessDate(bDate);
    const todayStr = new Date().toLocaleDateString('en-CA');
    const isToday = Boolean(bDate && bDate === todayStr);
    tag.textContent = isToday ? `Fresh today · ${wd} ${now.getDate()} ${mon}` : `Archived · ${formatted}`;
    tag.className = 'freshness-tag' + (isToday ? ' fresh' : ' stale');
    tag.title = isToday ? "Today's fresh briefing" : `Archived briefing from ${formatted}`;
  }

  const dateOverline = $('dateOverline');
  if (dateOverline) {
    dateOverline.textContent = '';
    dateOverline.classList.add('hidden');
  }
  updateMenuDrawer();
}

/* ------------------------------------------------------------------ notice */
/** Sleek, compact status bar when today's brief isn't ready or is loading. */
function renderNotice() {
  const box = $('notice');
  if (state.briefingLoading) {
    box.replaceChildren(h('div', { class: 'glass notice-compact loading-card', role: 'status' },
      h('span', { class: 'spinner', 'aria-hidden': 'true' }),
      h('span', { class: 'notice-text' }, "Checking for today's briefing…")));
    return;
  }
  if (!state.briefing) {
    box.replaceChildren(h('div', { class: 'glass notice-compact', role: 'status' },
      h('span', { class: 'notice-badge' }, 'SCHEDULED'),
      h('span', { class: 'notice-text' }, "Today's briefing records daily at sunrise. Check back shortly.")));
    return;
  }
  if (state.briefing.fresh === false) {
    box.replaceChildren(h('div', { class: 'glass notice-compact', role: 'status' },
      h('span', { class: 'notice-badge' }, 'ARCHIVED'),
      h('span', { class: 'notice-text' }, `Playing latest from ${chipLabel(state.briefing.date)} · Today's brief arrives before sunrise`)));
    return;
  }
  if (state.briefing.voice?.isFallback && state.briefing.voice?.requested) {
    const reqName = voiceName(state.briefing.voice.requested);
    box.replaceChildren(h('div', { class: 'glass notice-compact', role: 'status' },
      h('span', { class: 'notice-badge' }, 'VOICE NOTE'),
      h('span', { class: 'notice-text' }, `${reqName} is not yet voiced for ${chipLabel(state.briefing.date)} · Narrated by ${state.briefing.voice.name}`)));
    return;
  }
  box.replaceChildren();
}

/* ------------------------------------------------------------- guest & auth */
function openSignIn(reason = 'default') {
  const modal = $('signin');
  if (!modal) return;
  modal.classList.remove('hidden');
  const errEl = $('loginError');
  if (errEl) { errEl.textContent = ''; errEl.classList.add('hidden'); }
  const title = $('signinTitle');
  const hint = $('loginHint');
  if (title) {
    title.textContent = reason === 'push' ? 'Connect for notifications' : 'Sign in to Hark Daily';
  }
  if (hint) {
    hint.textContent = reason === 'push'
      ? 'Sign in once to receive your morning brief notification before sunrise.'
      : 'Sign in to sync your preferences and sources across your devices and the Android app.';
  }
  $('providerStep')?.classList.remove('hidden');
  $('emailForm')?.classList.add('hidden');
  $('sentStep')?.classList.add('hidden');
}

function closeSignIn() {
  const modal = $('signin');
  if (modal) modal.classList.add('hidden');
}
window.openSignIn = openSignIn;
window.closeSignIn = closeSignIn;

function renderGuestBanner() {
  const banner = $('guestBanner');
  if (!banner) return;
  const isGuest = !state.profile;
  const dismissed = localStorage.getItem('mb-guest-banner-dismissed') === 'true';

  const nativeGranted = window.HarkNative && window.HarkNative.hasNotificationPermission();
  const webGranted = typeof Notification !== 'undefined' && Notification.permission === 'granted';
  const granted = Boolean(nativeGranted || webGranted);

  if (!isGuest || dismissed || granted) {
    banner.classList.add('hidden');
    return;
  }
  banner.classList.remove('hidden');

  // Push status on banner button
  const pushBtn = $('bannerPushBtn');
  if (pushBtn) {
    const span = pushBtn.querySelector('span');
    if (span) span.textContent = 'Enable notifications';
    pushBtn.classList.remove('glass-btn');
  }

  // Install button visibility
  const installBtn = $('bannerInstallBtn');
  if (installBtn) {
    installBtn.classList.toggle('hidden', Boolean(window.HarkNative) || !installMode());
  }
}

/* -------------------------------------------------------------------- hero */
/** Podcast needs the front-end switch (config.js) and the server flag (app_status) both on. */
function podcastOn() {
  return FEATURES.podcast && state.status?.podcast?.enabled !== false;
}

/** The edition to build: defaults to Podcast when available, falls back to Full. */
function activeMode() {
  if (state.mode === 'rapid') return FEATURES.rapid ? 'rapid' : (podcastOn() ? 'podcast' : 'full');
  return podcastOn() ? 'podcast' : 'full';
}

function syncModePicker() {
  const fullBtn = $('modeFullBtn');
  const rapidBtn = $('modeRapidBtn');
  const podcastBtn = $('modePodcastBtn');
  const hero = $('hero');
  const mode = activeMode();
  const isRapid = mode === 'rapid';

  rapidBtn?.classList.toggle('hidden', !FEATURES.rapid);
  podcastBtn?.classList.toggle('hidden', !podcastOn());
  // A single edition needs no switcher.
  $('briefModeBar')?.classList.toggle('hidden', !FEATURES.rapid && !podcastOn());
  for (const [btn, key] of [[podcastBtn, 'podcast'], [fullBtn, 'full'], [rapidBtn, 'rapid']]) {
    if (!btn) continue;
    btn.classList.toggle('on', mode === key);
    btn.setAttribute('aria-checked', String(mode === key));
  }
  if (hero) {
    hero.classList.toggle('is-rapid', isRapid);
  }

  // Update Clean Player format switcher
  const cleanPodcast = $('cleanFormatPodcast');
  const cleanFull = $('cleanFormatFull');
  if (cleanPodcast) cleanPodcast.classList.toggle('active', mode === 'podcast');
  if (cleanFull) cleanFull.classList.toggle('active', mode !== 'podcast');
  const cleanEst = $('cleanBriefEst');
  if (cleanEst && state.briefing?.duration) {
    cleanEst.textContent = `${Math.round(state.briefing.duration / 60)} min`;
  }
}

function setBriefingMode(mode) {
  if (state.mode === mode) return;
  state.mode = mode;
  store.set('brief-mode', mode);
  syncModePicker();
  $('podcastVoiceBanner')?.classList.add('hidden');
  trackEvent('select_content', { content_type: 'briefing_mode', item_id: mode });

  if (state.packContext) {
    const { rows, settings, date, notes, fresh, podcastClips } = state.packContext;
    const targetInfo = getTargetStoryInfo();
    const briefing = buildPackBriefing(rows, settings, {
      date,
      voice: settings.voice,
      notes,
      mode: activeMode(),
      podcastClips,
      targetStory: targetInfo.story,
      targetTitle: targetInfo.title,
      targetAudio: targetInfo.audio,
      targetSource: targetInfo.source,
      targetDur: targetInfo.dur,
      targetHash: targetInfo.hash,
      edition: state.edition,
    });
    if (briefing) {
      briefing.fresh = fresh;
      const wasPlaying = player.isPlaying;
      state.briefing = briefing;
      displayBriefing();
      if (wasPlaying) {
        player.audio.play().catch(() => {});
      }
      if (briefing.podcastFallback) toast("Podcast isn't ready today, so here's the full brief.");
      else toast(mode === 'rapid' ? 'Rapid Fire active · Top 5 stories @ 1.1x speed ⚡'
        : mode === 'podcast' ? 'Podcast active · two hosts, same news 🎙️' : 'Full Edition active ☀️');
    }
  }
}
window.setBriefingMode = setBriefingMode;

function syncEditionPicker() {
  const sel = $('editionSelect');
  if (sel) sel.value = state.edition;
  const flag = $('editionFlag');
  if (flag) {
    const ed = EDITIONS[state.edition] || EDITIONS.ca;
    if (ed.flagSvg) {
      flag.innerHTML = ed.flagSvg;
    } else {
      flag.textContent = ed.flag || '🇨🇦';
    }
  }
  const label = $('editionLabel');
  if (label) label.textContent = (EDITIONS[state.edition]?.code || state.edition || 'ca').toUpperCase();
}

export async function setEdition(edition) {
  if (!EDITIONS[edition]) return;
  const wasPlaying = player.isPlaying;

  // Stop currently playing audio immediately and reset timeline
  player.audio.pause();
  player.audio.currentTime = 0;
  player.index = 0;
  if (player.preloader) {
    delete player.preloader.dataset.clip;
    player.preloader.removeAttribute('src');
  }

  state.edition = edition;
  store.set('edition', edition);
  syncEditionPicker();
  updateMenuDrawer();
  trackEvent('select_content', { content_type: 'edition', item_id: edition });

  const today = new Date().toLocaleDateString('en-CA');
  const currentRows = state.packContext?.rows || [];
  const targetNeedsLoad =
    (edition === 'in' && !currentRows.some((r) => r.section && r.section.endsWith('_in'))) ||
    (edition === 'us' && !currentRows.some((r) => r.section && r.section.endsWith('_us'))) ||
    (edition === 'ca' && state.briefing?.date !== today && currentRows.some((r) => r.section && r.section.endsWith('_in')));

  if (targetNeedsLoad) {
    const pack = await loadStoryPack(today);
    if (pack) {
      state.briefing = pack;
      const posKey = posKeyFor(pack);
      store.set(posKey, 0);
      displayBriefing();
      if (wasPlaying) {
        player.loadClip(0, { seek: 0, autoplay: true });
      } else {
        player.loadClip(0, { seek: 0, autoplay: false });
        player.tick();
      }
      const ed = EDITIONS[edition];
      toast(`Switched to ${ed?.name || edition} ${ed?.flag || ''}`);
      return;
    }
  }

  if (state.packContext) {
    const { rows, settings, date, notes, fresh, podcastClips } = state.packContext;
    const targetInfo = getTargetStoryInfo();
    const briefing = buildPackBriefing(rows, settings, {
      date,
      voice: settings.voice,
      notes,
      mode: activeMode(),
      podcastClips,
      targetStory: targetInfo.story,
      targetTitle: targetInfo.title,
      targetAudio: targetInfo.audio,
      targetSource: targetInfo.source,
      targetDur: targetInfo.dur,
      targetHash: targetInfo.hash,
      edition: state.edition,
    });
    if (briefing && briefing.stories && briefing.stories.length > 0) {
      briefing.fresh = fresh;
      briefing.edition = edition;

      // Reset saved position for this edition so we restart fresh
      const posKey = posKeyFor(briefing);
      store.set(posKey, 0);

      state.briefing = briefing;
      displayBriefing();

      // Restart player with the new country's content from the beginning (Story 1 / clip 0)
      if (wasPlaying) {
        player.loadClip(0, { seek: 0, autoplay: true });
      } else {
        player.loadClip(0, { seek: 0, autoplay: false });
        player.tick();
      }

      const ed = EDITIONS[edition];
      toast(`Switched to ${ed?.name || edition} ${ed?.flag || ''}`);
    } else {
      const ed = EDITIONS[edition];
      toast(`${ed?.name || edition} stories are not available yet.`, { error: true });
    }
  }
}
window.setEdition = setEdition;

function renderHero() {
  $('hero').classList.toggle('hidden', !state.briefing);
  syncModePicker();
}

function renderPersonas() {
  const row = $('personaRow');
  if (!row) return;
  const isPodcast = activeMode() === 'podcast';
  const activeVoiceId = state.briefing?.voice?.id || state.profile?.settings?.voice || DEFAULT_VOICE_ID;
  const available = new Set(state.briefing?.availableVoices || []);
  const hintEl = $('narratorSheetHint');
  if (hintEl) {
    hintEl.textContent = isPodcast
      ? 'Podcast mode uses pre-selected co-hosts (Matthew & Kelly). Switch to Full Brief on the player to customize your narrator.'
      : 'All four narrators read the daily briefing for the Full Brief edition. Pick who you\'d like to hear.';
  }
  row.replaceChildren(...VOICES.map((v) => {
    const on = !isPodcast && v.id === activeVoiceId;
    const isReady = available.size === 0 || available.has(v.id);
    const btn = h('button', {
      type: 'button',
      class: 'persona' + (on ? ' on' : '') + (!isReady ? ' unready' : ''),
      'aria-pressed': String(on),
      dataset: { voice: v.id },
    },
      h('span', { class: 'persona-avatar' }, icon(v.icon || 'mic')),
      h('span', { class: 'persona-text' },
        h('span', { class: 'persona-name' }, v.name),
        h('span', { class: 'persona-desc' }, isPodcast ? `Switch to Full Brief with ${v.name}` : (isReady ? (v.style || v.desc) : 'Pending for today'))
      ),
      isReady ? null : h('span', { class: 'persona-status' }, 'Pending')
    );
    btn.addEventListener('click', async () => {
      if (isPodcast) {
        state.mode = 'full';
        store.set('brief-mode', 'full');
        syncModePicker();
        $('podcastVoiceBanner')?.classList.add('hidden');
      }
      if (v.id === activeVoiceId && !isPodcast) {
        $('narratorSheet')?.close();
        return;
      }
      btn.classList.add('busy');
      try {
        await api.saveSettings({ voice: v.id });
        if (state.profile?.settings) state.profile.settings.voice = v.id;
        toast(`Switching narrator to ${v.name}…`);
        const targetDate = state.briefing?.date || new Date().toLocaleDateString('en-CA');
        const pack = await loadStoryPack(targetDate);
        if (pack) {
          const currentPos = player.position;
          const wasPlaying = player.isPlaying;
          state.briefing = pack;
          displayBriefing();
          player.seekTo(currentPos);
          if (wasPlaying) player.audio.play().catch(() => {});
          if (pack.voice?.id === v.id) {
            toast(`Now playing: read by ${v.name}.`);
          } else {
            toast(`${v.name}'s recording isn't ready for this edition yet. Playing ${pack.voice.name} instead.`, { error: true });
          }
        } else {
          toast(`${v.name}'s recording isn't ready for this edition yet.`, { error: true });
        }
        $('narratorSheet')?.close();
      } catch (err) {
        toast(err.message, { error: true });
      } finally {
        btn.classList.remove('busy');
      }
    });
    return btn;
  }));
}


/* -------------------------------------------------------------- date chips */
function chipLabel(date) {
  const today = new Date().toLocaleDateString('en-CA');
  if (date === today) return 'Today';
  const y = new Date(); y.setDate(y.getDate() - 1);
  if (date === y.toLocaleDateString('en-CA')) return 'Yesterday';
  return new Date(`${date}T12:00`).toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short' });
}

function renderDateChips() {
  const box = $('dateChips');
  const card = $('archiveCard');
  if (!box) return;
  const dates = state.archiveDates;
  const show = dates.length >= 2;
  box.classList.toggle('hidden', !show);
  if (card) card.classList.toggle('hidden', !show);
  box.replaceChildren(...dates.map((d) => {
    const isCur = d === state.briefing?.date;
    const b = h('button', { class: 'dchip' + (isCur ? ' active' : ''), type: 'button' },
      h('span', {}, chipLabel(d)),
      h('small', {}, isCur ? 'Active' : d)
    );
    b.addEventListener('click', () => selectDate(d));
    return b;
  }));
}

async function selectDate(date) {
  try {
    const pack = await loadStoryPack(date);
    if (pack) {
      state.briefing = pack;
      displayBriefing();
      return;
    }
    state.briefing = null;
    displayBriefing();
  } catch (err) {
    toast(err.message, { error: true });
  }
}

/* ----------------------------------------------------------------- sections */
function audioLen(story) {
  const secs = Math.round((story.end || 0) - (story.start || 0));
  return secs < 60 ? `${secs}s audio` : `${fmtTime(secs)}`;
}

function storyRow(story) {
  const sec = SECTIONS[story.section] || SECTIONS.top;
  const secKey = story.section || 'top';
  const row = h('article', {
    class: `story-row cat-${secKey}`,
    style: `--cat: var(--c-${secKey}, var(--accent));`,
    dataset: { id: story.id },
  });

  const dot = h('button', { class: 'play-dot', type: 'button', 'aria-label': `Play from: ${story.headline}` },
    icon('play', 'i-play'),
    icon('pause', 'i-pause'),
    h('span', { class: 't' }, fmtTime(story.start || 0)));

  dot.addEventListener('click', (e) => {
    e.stopPropagation();
    if (player.current === story.id) {
      player.toggle();
    } else {
      player.playChapter(story.id);
      $('lineupSheet')?.close();
    }
  });
  row.addEventListener('click', () => {
    player.playChapter(story.id);
    $('lineupSheet')?.close();
  });

  const catTile = h('div', { class: `story-tile cat-tile cat-${secKey}` },
    icon(sec.icon || 'globe'),
    h('span', { class: 'eq', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i'))
  );

  const main = h('div', { class: 'story-main' },
    catTile,
    h('div', { class: 'story-text' },
      h('div', { class: 'story-meta' },
        h('span', { class: `badge badge-cat cat-${secKey}` }, sec.title),
        h('span', { class: 'dur' }, icon('clock'), audioLen(story)),
        story.source ? h('span', {}, '·') : null,
        story.source ? h('span', {}, story.source) : null,
        story.also?.length ? h('span', {}, `· +${story.also.length} source${story.also.length === 1 ? '' : 's'}`) : null,
        h('button', {
          class: 'story-quick-share',
          type: 'button',
          'aria-label': `Share "${story.headline}"`,
          title: 'Share article',
          onclick: (e) => {
            e.stopPropagation();
            openShareModal(story);
          },
        }, icon('share'))
      ),
      h('h3', {}, story.headline),
      story.summary ? h('p', { class: 'story-snippet' }, story.summary) : null
    ),
    story.image ? h('img', {
      class: 'story-thumb', src: story.image, alt: '', loading: 'lazy', decoding: 'async',
      referrerpolicy: 'no-referrer', onerror: (e) => e.target.remove(),
    }) : null,
    dot
  );

  const detail = h('div', { class: 'story-detail hidden' },
    h('p', { class: 'summary' }, story.summary),
    story.also?.length ? h('p', { class: 'also' }, `Also covered by ${story.also.join(', ')}`) : null,
    h('div', { class: 'story-actions' },
      h('button', { class: 'pill-btn sm', type: 'button', onclick: () => player.playChapter(story.id) }, icon('play'), 'Play from here'),
      story.url ? h('a', { class: 'pill-btn glass-btn sm', href: story.url, target: '_blank', rel: 'noopener noreferrer' }, 'Read article', icon('external')) : null,
      h('button', {
        class: 'pill-btn glass-btn sm story-share-btn',
        type: 'button',
        'aria-label': `Share "${story.headline}"`,
        onclick: (e) => {
          e.stopPropagation();
          openShareModal(story);
        },
      }, icon('share'), 'Share')
    ),
    reportRow(story)
  );

  main.addEventListener('click', () => {
    const isExpanded = row.classList.toggle('expanded');
    detail.classList.toggle('hidden', !isExpanded);
  });
  row.append(main, detail);
  return row;
}

function reportRow(story) {
  const reported = state.reported.has(story.id);
  const btn = h('button', { class: 'report-row', type: 'button' },
    icon('flag'), reported ? 'Reported. Thanks' : 'Report this summary');
  if (!reported) btn.addEventListener('click', (e) => { e.stopPropagation(); openReport(story, btn); });
  return btn;
}

/* ------------------------------------------------------------- story sharing */
export function buildStoryShareUrl(story, date, origin = window.location.origin) {
  const key = storyKey(story) || story?.id || '';
  if (date) return `${origin}/s/${date}/${key}`;
  return `${origin}/?story=${encodeURIComponent(key)}`;
}

export async function openShareModal(story) {
  if (!story) return;
  const briefing = state.briefing;
  const date = briefing?.date || '';
  const shareUrl = buildStoryShareUrl(story, date);

  const shareData = {
    title: story.headline,
    text: story.headline,
    url: shareUrl,
  };

  if (navigator.share && /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent)) {
    try {
      trackEvent('share', {
        method: 'web_share_api',
        content_type: 'story',
        item_id: story.id,
        item_name: story.headline,
        section: story.section || 'top',
      });
      await navigator.share(shareData);
      return;
    } catch (err) {
      if (err.name === 'AbortError') return;
    }
  }

  trackEvent('share_modal_open', {
    content_type: 'story',
    item_id: story.id,
    item_name: story.headline,
    section: story.section || 'top',
  });

  showShareSheet(story, shareUrl, shareData);
}
window.openShareModal = openShareModal;

function showShareSheet(story, shareUrl, shareData) {
  const sheet = $('shareSheet');
  if (!sheet) return;

  const baseSec = (story.section || 'top').replace(/_(us|in|ca)$/, '');
  const sec = SECTIONS[story.section] || SECTIONS[baseSec] || SECTIONS.top;
  const catEl = $('sharePreviewCat');
  if (catEl) {
    catEl.textContent = story.source || sec.title;
    catEl.className = `badge badge-cat cat-${baseSec}`;
  }

  const durEl = $('sharePreviewDurText');
  if (durEl) durEl.textContent = audioLen(story);

  const titleEl = $('sharePreviewTitle');
  if (titleEl) titleEl.textContent = story.headline;

  const summaryEl = $('sharePreviewSummary');
  if (summaryEl) summaryEl.textContent = story.summary || '';

  const inputEl = $('shareLinkInput');
  if (inputEl) inputEl.value = shareUrl;

  const copyBtn = $('shareCopyBtn');
  const copyText = $('shareCopyBtnText');
  const doCopy = async () => {
    trackEvent('share', {
      method: 'copy_link',
      content_type: 'story',
      item_id: story.id,
      item_name: story.headline,
      section: story.section || 'top',
    });
    try {
      await navigator.clipboard.writeText(shareUrl);
      if (copyText) copyText.textContent = 'Copied! ✓';
      toast('Story link copied to clipboard!');
      setTimeout(() => { if (copyText) copyText.textContent = 'Copy Link'; }, 2000);
    } catch {
      inputEl?.select();
      document.execCommand('copy');
      if (copyText) copyText.textContent = 'Copied! ✓';
      toast('Story link copied to clipboard!');
      setTimeout(() => { if (copyText) copyText.textContent = 'Copy Link'; }, 2000);
    }
  };

  if (copyBtn) copyBtn.onclick = doCopy;

  const xBtn = $('shareXBtn');
  if (xBtn) {
    xBtn.href = `https://twitter.com/intent/tweet?text=${encodeURIComponent(story.headline)}&url=${encodeURIComponent(shareUrl)}`;
    xBtn.onclick = () => {
      trackEvent('share', {
        method: 'x_twitter',
        content_type: 'story',
        item_id: story.id,
        item_name: story.headline,
        section: story.section || 'top',
      });
    };
  }

  const linkedInBtn = $('shareLinkedInBtn');
  if (linkedInBtn) {
    linkedInBtn.href = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`;
    linkedInBtn.onclick = () => {
      trackEvent('share', {
        method: 'linkedin',
        content_type: 'story',
        item_id: story.id,
        item_name: story.headline,
        section: story.section || 'top',
      });
    };
  }

  const whatsAppBtn = $('shareWhatsAppBtn');
  if (whatsAppBtn) {
    whatsAppBtn.href = `https://api.whatsapp.com/send?text=${encodeURIComponent(`${story.headline}\n${shareUrl}`)}`;
    whatsAppBtn.onclick = () => {
      trackEvent('share', {
        method: 'whatsapp',
        content_type: 'story',
        item_id: story.id,
        item_name: story.headline,
        section: story.section || 'top',
      });
    };
  }

  const nativeBtn = $('shareNativeAction');
  if (nativeBtn) {
    if (navigator.share) {
      nativeBtn.classList.remove('hidden');
      nativeBtn.onclick = async () => {
        trackEvent('share', {
          method: 'web_share_api',
          content_type: 'story',
          item_id: story.id,
          item_name: story.headline,
          section: story.section || 'top',
        });
        try {
          await navigator.share(shareData);
          sheet.close();
        } catch { /* cancelled */ }
      };
    } else {
      nativeBtn.classList.add('hidden');
    }
  }

  navigator.clipboard?.writeText(shareUrl).then(() => {
    toast('Link copied to clipboard! Share it with friends.');
  }).catch(() => {});

  sheet.showModal();
}

function getTargetStoryInfo() {
  if (window.__SHARED_STORY__) {
    const s = window.__SHARED_STORY__;
    const hashMatch = (s.hash || s.key || s.audio || s.slug || s.story || '').match(/(?:-|^)([0-9a-f]{8})(?:\.mp3)?$/i);
    const hash = hashMatch ? hashMatch[1].toLowerCase() : null;
    return {
      story: s.story || hash || null,
      title: s.title || null,
      audio: s.audio || null,
      dur: Number.parseInt(String(s.dur || '20'), 10),
      source: s.source || null,
      date: s.date || null,
      hash,
    };
  }
  const pathMatch = window.location.pathname.match(/^\/s\/(\d{4}-\d{2}-\d{2})\/([^/?#]+)/);
  if (pathMatch) {
    const [, pathDate, rawSlug] = pathMatch;
    if (/^[0-9a-f]{8}$/i.test(rawSlug)) {
      const key = rawSlug.toLowerCase();
      return {
        story: key,
        title: null,
        audio: null,
        dur: 20,
        source: null,
        date: pathDate,
        hash: key,
      };
    }
    const slugMatch = rawSlug.match(/^([a-z0-9_]+-\d+)(?:-([0-9a-f]{8}))?$/i);
    return {
      story: slugMatch ? slugMatch[1] : rawSlug,
      title: null,
      audio: null,
      dur: 20,
      source: null,
      date: pathDate,
      hash: slugMatch && slugMatch[2] ? slugMatch[2].toLowerCase() : null,
    };
  }
  const urlParams = new URLSearchParams(window.location.search);
  const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const story = urlParams.get('story') || hashParams.get('story') || null;
  const title = urlParams.get('title') || urlParams.get('t') || hashParams.get('title') || null;
  const audio = urlParams.get('audio') || urlParams.get('a') || hashParams.get('audio') || null;
  const dur = Number.parseInt(urlParams.get('dur') || hashParams.get('dur') || '20', 10);
  const source = urlParams.get('src') || urlParams.get('source') || hashParams.get('src') || null;
  const date = urlParams.get('date') || hashParams.get('date') || null;
  const hashMatch = (audio || story || '').match(/(?:-|^)([0-9a-f]{8})(?:\.mp3)?$/i);
  return {
    story,
    title,
    audio,
    dur,
    source,
    date,
    hash: hashMatch ? hashMatch[1].toLowerCase() : null,
  };
}

let lastDeepLinkedStory = null;
function handleStoryDeepLink(storyInfo) {
  if (!storyInfo || !state.briefing?.stories?.length) return;
  const { story: storyId, title, audio, hash } = typeof storyInfo === 'string' ? { story: storyInfo } : storyInfo;

  // 1. Match by unique 8-char story key first (region-agnostic reference key /s/:date/:key)
  let story = hash
    ? state.briefing.stories.find((s) => (s.key && s.key === hash.toLowerCase()) || storyKey(s) === hash.toLowerCase())
    : null;
  // 2. Match by title (resilient against morning/evening batch rank shifts!)
  if (!story && title) story = state.briefing.stories.find((s) => titlesMatch(s.headline, title));
  // 3. Match by exact audio path (handles dropped/archived morning clips)
  if (!story && audio) story = state.briefing.stories.find((s) => s.audio_path === audio);
  // 4. Fallback to ID or key
  if (!story && storyId) story = state.briefing.stories.find((s) => s.id === storyId || s.key === storyId);

  if (!story) {
    if (storyId || title) {
      trackEvent('shared_story_not_found', {
        requested_story: storyId || '',
        requested_title: title || '',
      });
    }
    return;
  }

  if (lastDeepLinkedStory !== story.id) {
    lastDeepLinkedStory = story.id;
    trackEvent('shared_story_opened', {
      story_id: story.id,
      story_title: story.headline,
      section: story.section || 'top',
      is_bonus: Boolean(story.isSharedBonus),
      share_param_story: storyId || '',
      share_param_date: new URLSearchParams(window.location.search).get('date') || '',
    });
    trackEvent('view_item', {
      content_type: 'shared_story',
      item_id: story.id,
      item_name: story.headline,
      item_category: story.section || 'top',
    });
  }

  document.title = `${story.headline} — Hark Daily`;
  player.seekTo(story.start || 0);

  const row = document.querySelector(`.story-row[data-id="${story.id}"]`);
  if (row) {
    row.classList.add('expanded', 'story-shared-target');
    const detail = row.querySelector('.story-detail');
    if (detail) detail.classList.remove('hidden');

    const meta = row.querySelector('.story-meta');
    if (meta && !meta.querySelector('.badge-shared')) {
      const badge = h('span', { class: 'badge badge-cat badge-shared' },
        h('span', { class: 'live-dot', 'aria-hidden': 'true' }),
        story.isSharedBonus ? 'Shared (earlier edition)' : 'Shared with you'
      );
      meta.prepend(badge);
    }

    setTimeout(() => {
      row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 400);
  }

  const banner = $('sharedStoryBanner');
  if (banner) {
    const hl = $('sharedStoryHeadline');
    if (hl) hl.textContent = story.headline;
    const sub = $('sharedStorySubtitle');
    if (sub) {
      const dur = Math.round(story.end - story.start) || 20;
      sub.textContent = `${story.source || 'The news'} · ~${dur}s audio · ${story.isSharedBonus ? "From today's earlier edition · " : ''}No account required`;
    }
    const playBtn = $('sharedStoryPlayBtn');
    if (playBtn) {
      playBtn.onclick = () => {
        trackEvent('shared_story_play', {
          story_id: story.id,
          story_title: story.headline,
          section: story.section || 'top',
          is_bonus: Boolean(story.isSharedBonus),
        });
        player.playChapter(story.id);
        banner.classList.add('hidden');
      };
    }
    const browseBtn = $('sharedStoryBrowseBtn');
    if (browseBtn) {
      browseBtn.onclick = () => {
        trackEvent('shared_story_browse', {
          story_id: story.id,
          story_title: story.headline,
        });
        banner.classList.add('hidden');
        row?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      };
    }
    $('sharedStoryCloseBtn')?.addEventListener('click', () => {
      trackEvent('shared_story_dismiss', {
        story_id: story.id,
      });
      banner.classList.add('hidden');
    });
    banner.classList.remove('hidden');
  }
}

function renderSections() {
  const box = $('sections');
  const b = state.briefing;
  const listHead = $('listHead');
  const storyCount = $('storyCount');

  if (!b) {
    if (listHead) listHead.classList.add('hidden');
    box.replaceChildren(h('div', { class: 'empty' }, h('h3', {}, 'Not published yet'),
      h('p', {}, "Today's brief is recorded once each morning for everyone. Reload in a minute, or set your topics in Sources.")));
    return;
  }

  if (listHead) {
    listHead.classList.remove('hidden');
    if (storyCount) storyCount.textContent = `${b.stories.length}`;
  }

  const currentSection = (() => {
    const ch = player.chapters.find((c) => c.id === player.current);
    return b.stories.find((s) => s.id === ch?.id)?.section;
  })();

  let secNum = 1;
  const blocks = (b.sections || []).flatMap((sec) => {
    const stories = b.stories.filter((s) => s.section === sec.key);
    if (!stories.length) return [];
    const here = currentSection === sec.key;
    const head = h('div', { class: 'section-head' },
      h('span', { class: 'num' }, String(secNum++).padStart(2, '0')),
      h('span', { class: 'overline' }, sec.title),
      h('span', { class: 'count' }, `· ${stories.length} ${stories.length === 1 ? 'story' : 'stories'}`),
      here
        ? h('span', { class: 'here' }, h('span', { class: 'live-dot', 'aria-hidden': 'true' }), player.isPlaying ? 'Playing' : 'Paused')
        : h('button', {
            class: 'play-section', type: 'button',
            'aria-label': `Play ${sec.title}`,
            onclick: () => { player.seekTo(stories[0].start || 0); player.audio.play().catch(() => {}); },
          }, icon('play'), 'Play section')
    );
    const list = h('div', { class: 'section-list' }, ...stories.map(storyRow));
    const block = h('div', { class: 'section-block', dataset: { section: sec.key } }, head, list);
    return [block];
  });

  box.replaceChildren(...blocks);
  syncPlaying();
  followChapter();
  applySearch($('searchInput')?.value);
}

/* ----------------------------------------------------------- search & text size */
let searchDebounceTimer = null;
function trackSearchQuery(q, matchCount) {
  clearTimeout(searchDebounceTimer);
  if (!q || q.length < 2) return;
  searchDebounceTimer = setTimeout(() => {
    trackEvent('search', { search_term: q, matches_found: matchCount });
  }, 800);
}

function applySearch(query) {
  const q = (query || '').trim().toLowerCase();
  const rows = document.querySelectorAll('.story-row');
  let matchCount = 0;
  rows.forEach((row) => {
    const id = row.dataset.id;
    const story = state.briefing?.stories.find((s) => s.id === id);
    if (!story) return;
    const text = `${story.headline} ${story.summary || ''} ${story.source || ''}`.toLowerCase();
    const match = !q || text.includes(q);
    row.classList.toggle('hidden', !match);
    if (match) matchCount++;
  });
  document.querySelectorAll('.section-block').forEach((block) => {
    const visibleStories = block.querySelectorAll('.story-row:not(.hidden)');
    block.classList.toggle('hidden', visibleStories.length === 0);
  });
  let empty = document.getElementById('searchEmptyNotice');
  if (q && matchCount === 0) {
    if (!empty) {
      empty = h('div', { id: 'searchEmptyNotice', class: 'search-empty' },
        h('h3', {}, 'No stories found'),
        h('p', {}, `No stories match "${query}".`)
      );
      $('sections')?.appendChild(empty);
    }
  } else if (empty) {
    empty.remove();
  }
  trackSearchQuery(q, matchCount);
}

function setTextSize(size) {
  document.documentElement.dataset.textSize = size;
  try { localStorage.setItem('mb-text-size', size); } catch { /* ignore */ }
  document.querySelectorAll('#textSize button').forEach((btn) => {
    btn.classList.toggle('on', btn.dataset.size === size);
  });
}

function syncPlaying() {
  const id = player.current;
  document.querySelectorAll('.story-row').forEach((row) => {
    const on = row.dataset.id === id;
    row.classList.toggle('current', on);
    row.classList.toggle('playing-now', on && player.isPlaying);
    const dot = row.querySelector('.play-dot');
    if (!dot) return;
    const label = on && player.isPlaying ? 'Pause' : `Play from: ${row.querySelector('h3')?.textContent || ''}`;
    dot.setAttribute('aria-label', label);
  });
}

/**
 * Reading along: the story being read stays open and in view, unless the listener is
 * scrolling themselves — then we keep our hands off the page for a few seconds.
 */
function followChapter() {
  const id = player.current;
  let row = null;
  document.querySelectorAll('.story-row').forEach((r) => {
    const mine = r.dataset.id === id;
    if (mine) row = r;
    r.querySelector('.story-detail')?.classList.toggle('hidden', !mine);
  });
  if (!id || !row || !player.isPlaying || Date.now() - lastScroll < 8000) return;
  if (player.heroInView) return; // Don't scroll window away from hero card while user is reading along
  window.scrollTo({ top: row.getBoundingClientRect().top + window.scrollY - 96, behavior: 'smooth' });
}

/* ------------------------------------------------------------------ report */
const REPORT_REASONS = [['inaccurate', 'Wrong or misleading'], ['offensive', 'Offensive or harmful'], ['broken', "Doesn't match the article"], ['other', 'Something else']];
let reportStory = null;
let reportReason = null;
/** When the listener last scrolled, so follow-along can stay out of their way. */
let lastScroll = 0;

function openReport(story, btn) {
  reportStory = story;
  reportReason = null;
  const box = $('reportReasons');
  box.replaceChildren(...REPORT_REASONS.map(([key, label]) => {
    const b = h('button', { class: 'chip-btn', type: 'button', 'aria-pressed': 'false' }, label);
    b.addEventListener('click', () => {
      reportReason = key;
      box.querySelectorAll('.chip-btn').forEach((x) => { const on = x === b; x.classList.toggle('active', on); x.setAttribute('aria-pressed', String(on)); });
    });
    return b;
  }));
  $('reportNote').value = '';
  $('reportError').textContent = '';
  $('reportSheet').showModal();
}

async function sendReport() {
  if (!reportReason) { $('reportError').textContent = 'Pick a reason first.'; return; }
  const s = reportStory;
  $('reportSend').disabled = true;
  try {
    await api.report({
      reason: reportReason,
      note: $('reportNote').value.trim().slice(0, 1000) || null,
      headline: s.headline, summary: s.summary, url: s.url, source: s.source,
    });
    state.reported.add(s.id);
    store.set('reported', [...state.reported]);
    $('reportSheet').close();
    toast('Reported. Thanks for flagging it.');
    renderSections();
  } catch (err) {
    $('reportError').textContent = err.message;
  } finally {
    $('reportSend').disabled = false;
  }
}

/** The day's shared clips assembled for this listener; null when there is no pack at all.
 *
 * Today's pack may not be published yet (the nightly job hasn't run), so for today only we fall
 * back to the most recent one and flag it, rather than showing an empty player.
 * For international editions like India, data naturally stems from the previous day's evening run
 * until the next evening run updates it. */
async function loadStoryPack(day) {
  const today = new Date().toLocaleDateString('en-CA');
  const targetDay = day || today;
  const targetEd = state.edition || 'ca';
  try {
    // Parallelize settings and day queries concurrently
    const [{ settings }, rows, notes, podcastClips] = await Promise.all([
      api.settings(),
      api.storyAudio(targetDay),
      api.voiceNotes(targetDay),
      podcastOn() ? api.podcastClips(targetDay).catch(() => []) : Promise.resolve([])
    ]);

    let date = targetDay;
    let actualRows = rows;
    let actualNotes = notes;
    let actualPodcast = podcastClips;

    // Check whether the queried day actually has stories for the listener's chosen country edition.
    // For example, India edition is voiced in the evening run, so in the morning EST it picks up
    // naturally from the previous day's evening run until today's evening run publishes.
    const hasEditionRows = (rList) => {
      if (!rList || !rList.length) return false;
      if (targetEd === 'in') return rList.some((r) => r.section && r.section.endsWith('_in'));
      if (targetEd === 'us') return rList.some((r) => r.section && r.section.endsWith('_us'));
      return rList.some((r) => r.section === 'top' || (r.section && !r.section.endsWith('_us') && !r.section.endsWith('_in')));
    };

    const targetInfo = getTargetStoryInfo();
    const sharedRowsFromTargetDay = targetInfo.hash
      ? (rows || []).filter((r) => storyKey(r) === targetInfo.hash)
      : [];

    if ((!actualRows.length || !hasEditionRows(actualRows)) && (targetDay === today || sharedRowsFromTargetDay.length > 0)) {
      const latest = await api.latestStoryDate(targetEd);
      if (latest && latest !== targetDay) {
        date = latest;
        [actualRows, actualNotes, actualPodcast] = await Promise.all([
          api.storyAudio(date),
          api.voiceNotes(date),
          podcastOn() ? api.podcastClips(date).catch(() => []) : Promise.resolve([])
        ]);
        if (sharedRowsFromTargetDay.length > 0) {
          for (const sr of sharedRowsFromTargetDay) {
            if (!actualRows.some((r) => storyKey(r) === storyKey(sr))) {
              actualRows.push(sr);
            }
          }
        }
      }
    }
    if (!actualRows.length) return null;

    const briefing = buildPackBriefing(actualRows, settings, {
      date,
      voice: settings.voice,
      notes: actualNotes,
      mode: activeMode(),
      podcastClips: actualPodcast,
      targetStory: targetInfo.story,
      targetTitle: targetInfo.title,
      targetAudio: targetInfo.audio,
      targetSource: targetInfo.source,
      targetDur: targetInfo.dur,
      targetHash: targetInfo.hash,
      edition: state.edition,
    });
    if (!briefing) return null;
    // A day is playable only once its narrator's clips and framing are all published. Without this
    // a pack that is mid-recording, or being re-recorded, plays two voices inside one brief.
    const hasReadyMarkers = actualNotes.some((n) => n.note_key === READY_KEY);
    if (hasReadyMarkers) {
      const voiceId = briefing.voice?.id || '';
      const hosts = voiceId.split('+').filter(Boolean);
      const isReady = actualNotes.some((n) => n.note_key === READY_KEY && n.voice === voiceId) || (
        hosts.length > 0 &&
        hosts.every((h) => actualNotes.some((n) => n.note_key === READY_KEY && n.voice === h))
      );
      if (!isReady) {
        if (targetDay === today) {
          const latest = await api.latestStoryDate(targetEd);
          if (latest && latest !== today) return loadStoryPack(latest);
        }
        return null;
      }
    }
    briefing.fresh = date === today;
    state.packContext = { rows: actualRows, settings, date, notes: actualNotes, fresh: briefing.fresh, podcastClips: actualPodcast };
    return briefing;
  } catch {
    return null;  // no pack that day, or the story_audio table isn't there yet
  }
}

/* ----------------------------------------------------------------- loading */
/** One honest line under the brief: where it came from, and who read it. */
function setFootnote() {
  const el = $('footnote');
  if (el) el.textContent = '';
}

function displayBriefing() {
  if (state.briefing) {
    player.load(state.briefing);
    try { store.set('last-briefing', { ...state.briefing, edition: state.edition }); } catch { /* ignore storage error */ }
  }
  setFootnote();
  renderHeader();
  renderHero();
  renderNotice();
  renderGuestBanner();
  renderPersonas();
  renderDateChips();
  renderSections();
  renderAllStoriesSheet();
  updateMenuDrawer();
  const storyInfo = getTargetStoryInfo();
  if (storyInfo.story || storyInfo.title || storyInfo.audio || storyInfo.hash) handleStoryDeepLink(storyInfo);
}
window.displayBriefing = displayBriefing;
window.updateMenuDrawer = updateMenuDrawer;
window.state = state;

async function loadArchive() {
  try {
    const [{ briefings }, storyDates] = await Promise.all([
      api.archive(),
      api.storyDates().catch(() => []),
    ]);
    state.archiveDates = [...new Set([...briefings.map((b) => b.date), ...storyDates])].sort().reverse();
  } catch { state.archiveDates = []; }
  renderDateChips();
}

/* ------------------------------------------------------------ tab pages */
async function switchTab(tab) {
  if (tab === 'admin' && !isAdmin(state.profile)) return;
  currentTab = tab;
  trackEvent('screen_view', { screen_name: tab });
  document.querySelectorAll('#tabbar .tab').forEach((t) => {
    const on = t.dataset.tab === tab;
    t.classList.toggle('active', on);
    if (on) t.setAttribute('aria-current', 'page'); else t.removeAttribute('aria-current');
  });
  for (const p of ['today', 'sources', 'settings', 'admin']) {
    document.getElementById(`page-${p}`)?.classList.toggle('hidden', p !== tab);
  }
  window.scrollTo({ top: 0 });
  if (tab === 'sources' && !sourcesPage) {
    sourcesPage = new SourcesPage({ onDirty: syncSaveBar });
    try { await sourcesPage.load(); } catch (err) { recordError(err, 'sourcesPage.load'); toast("Couldn't load your sources.", { error: true }); }
  }
  if (tab === 'settings' && !settingsPage) {
    settingsPage = new SettingsPage({
      onDirty: syncSaveBar,
      goSources: () => switchTab('sources'),
      email: state.profile?.email,
      setRate: (rate) => player.setRate(rate),
    });
    try { await settingsPage.load(); } catch (err) { recordError(err, 'settingsPage.load'); toast("Couldn't load settings.", { error: true }); }
  }
  if (tab === 'admin' && !adminPage) {
    adminPage = new AdminPage();
    try { await adminPage.load(); } catch (err) { recordError(err, 'adminPage.load'); toast("Couldn't load admin state.", { error: true, ms: 6000 }); }
  }
  // Back on Today the hero card takes over; the floating player returns when it scrolls away.
  if (tab === 'today') player.showMini();
  syncMini();
  syncSaveBar();
}

/** Floating mini-player docked above toolbar whenever a briefing is loaded. */
function syncMini() {
  const show = !!player.briefing;
  const mini = $('miniPlayer');
  if (mini) {
    mini.classList.toggle('show', show);
    mini.setAttribute('aria-hidden', show ? 'false' : 'true');
  }
}

function syncSaveBar() {
  const dirty = currentTab !== 'today' && (sourcesPage?.isDirty() || settingsPage?.isDirty());
  $('saveBar').classList.toggle('hidden', !dirty);
}

async function saveAll() {
  try {
    let storiesChanged = false;
    if (sourcesPage?.isDirty()) {
      await sourcesPage.save();
      storiesChanged = true;
    }
    if (settingsPage?.isDirty()) await settingsPage.save();
    toast('Saved.');
    if (storiesChanged && state.packContext) {
      if (sourcesPage?.draft?.stories) {
        state.packContext.settings = {
          ...state.packContext.settings,
          stories: sourcesPage.draft.stories,
          section_order: sourcesPage.draft.section_order,
        };
      }
      const { rows, settings, date, notes, fresh, podcastClips } = state.packContext;
      const targetInfo = getTargetStoryInfo();
      const briefing = buildPackBriefing(rows, settings, {
        date,
        voice: settings.voice,
        notes,
        mode: activeMode(),
        podcastClips,
        targetStory: targetInfo.story,
        targetTitle: targetInfo.title,
        targetAudio: targetInfo.audio,
        targetSource: targetInfo.source,
        targetDur: targetInfo.dur,
        targetHash: targetInfo.hash,
        edition: state.edition,
      });
      if (briefing) {
        briefing.fresh = fresh;
        const curStory = player.storyFor(player.currentChapter());
        const curStoryId = curStory?.id;
        const offset = curStory ? Math.max(0, player.position - (curStory.start || 0)) : 0;
        const wasPlaying = !player.audio.paused;
        state.briefing = briefing;
        displayBriefing();
        if (curStoryId) {
          const target = briefing.stories?.find((s) => s.id === curStoryId);
          if (target) {
            player.seekTo((target.start || 0) + offset);
            if (wasPlaying) player.audio.play().catch(() => {});
          } else {
            player.seekTo(0);
          }
        }
      }
    }
  } catch (err) {
    toast(err.message, { error: true });
  }
  syncSaveBar();
}

function discardAll() {
  sourcesPage?.discard();
  settingsPage?.discard();
  syncSaveBar();
  toast('Changes discarded.');
}

/* ----------------------------------------------------------- Clean Player (Mock UI) */
let deleteAccountSheet = null;
let sleepTimerMinutes = 0;
let sleepTimerId = null;
const SLEEP_TIMER_STEPS = [0, 15, 30, 45, 'brief'];

function updateMenuDrawer() {
  const formatVal = $('menuFormatVal');
  if (formatVal) {
    formatVal.textContent = 'Podcast · Two hosts';
  }
  const voicesVal = $('menuVoicesVal');
  if (voicesVal) {
    voicesVal.textContent = 'Matthew & Kelly';
  }
  const regVal = $('menuRegionVal');
  if (regVal) {
    const ed = EDITIONS[state.edition];
    regVal.textContent = ed?.name || state.edition?.toUpperCase() || 'Canada';
  }
  const authBtn = $('menuAuthBtn');
  if (authBtn) {
    if (state.profile?.email) {
      authBtn.textContent = `Sign out (${state.profile.email.split('@')[0]})`;
    } else {
      authBtn.textContent = 'Sign in';
    }
  }
  const sleepVal = $('menuSleepTimerVal');
  if (sleepVal) {
    sleepVal.textContent = sleepTimerMinutes === 0 ? 'Off' : (sleepTimerMinutes === 'brief' ? 'End of brief' : `${sleepTimerMinutes} min`);
  }
  const deleteBtn = $('menuDeleteAccountBtn');
  if (deleteBtn) {
    const hasAccount = !!(state.profile?.id || state.profile?.email);
    deleteBtn.classList.toggle('hidden', !hasAccount);
  }
}

function cycleSleepTimer() {
  const currentIdx = SLEEP_TIMER_STEPS.indexOf(sleepTimerMinutes);
  const nextIdx = (currentIdx + 1) % SLEEP_TIMER_STEPS.length;
  sleepTimerMinutes = SLEEP_TIMER_STEPS[nextIdx];
  if (sleepTimerId) {
    clearTimeout(sleepTimerId);
    sleepTimerId = null;
  }
  updateMenuDrawer();
  if (sleepTimerMinutes === 0) {
    toast('Sleep timer turned off');
  } else if (sleepTimerMinutes === 'brief') {
    toast('Sleep timer will pause at end of brief');
  } else {
    toast(`Sleep timer set for ${sleepTimerMinutes} minutes 🌙`);
    sleepTimerId = setTimeout(() => {
      const audio = player.audio;
      const initialVol = audio.volume;
      let step = 0;
      const fade = setInterval(() => {
        step += 1;
        audio.volume = Math.max(0, initialVol * (1 - step / 10));
        if (step >= 10) {
          clearInterval(fade);
          audio.pause();
          audio.volume = initialVol;
          sleepTimerMinutes = 0;
          updateMenuDrawer();
          toast('Sleep timer paused playback 🌙');
        }
      }, 250);
    }, sleepTimerMinutes * 60 * 1000);
  }
}

async function downloadOfflineAudio() {
  const b = state.briefing;
  if (!b || !b.audio_url) {
    toast("No audio available to download yet.", { error: true });
    return;
  }
  toast("Downloading briefing for offline listening…");
  try {
    const res = await fetch(b.audio_url);
    if (!res.ok) throw new Error("Download failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Hark_Daily_${b.date || 'briefing'}_${b.mode || 'podcast'}.mp3`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast("Briefing downloaded successfully! ✓");
  } catch (err) {
    window.open(b.audio_url, '_blank');
    toast("Opened briefing audio link");
  }
}

const EDITIONS_ORDER = ['ca', 'us', 'in'];
function cycleEdition() {
  const curIdx = EDITIONS_ORDER.indexOf(state.edition);
  const nextIdx = (curIdx + 1) % EDITIONS_ORDER.length;
  setEdition(EDITIONS_ORDER[nextIdx]);
}

function openAuxSheet(tab) {
  const aux = $('auxSheet');
  const title = $('auxTitle');
  if (title) {
    title.textContent = tab === 'sources' ? 'Sources & Topics' : (tab === 'settings' ? 'Settings' : 'Admin');
  }
  if (aux) aux.classList.remove('hidden');
  switchTab(tab);
}

function renderAllStoriesSheet() {
  const b = state.briefing;
  if (!b) return;

  const countBadge = $('openAllStoriesLabel');
  if (countBadge) countBadge.textContent = `All ${b.stories.length}`;

  const sub = $('allStoriesSub');
  if (sub) sub.textContent = `${b.stories.length} stories today · tap to start listening`;

  const grid = $('cleanTopicGrid');
  if (grid) {
    const ch = player.chapters.find((c) => c.id === player.current);
    const currentSection = b.stories.find((s) => s.id === ch?.id)?.section || 'top';

    const getTopicIcon = (key) => {
      switch (key) {
        case 'top':
          return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/></svg>`;
        case 'world':
          return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18"/></svg>`;
        case 'canada':
        case 'us':
        case 'in':
          return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s7-6 7-11a7 7 0 10-14 0c0 5 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>`;
        case 'business':
          return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 20V10M12 20V4M19 20v-7"/></svg>`;
        case 'tech':
        case 'ai':
          return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/></svg>`;
        case 'sports':
          return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M5 6c4 3 10 3 14 0M5 18c4-3 10-3 14 0"/></svg>`;
        default:
          return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10"/></svg>`;
      }
    };

    grid.replaceChildren(...(b.sections || []).map((sec) => {
      const stories = b.stories.filter((s) => s.section === sec.key || s.section === sec.logicalKey || (s.section && s.section.startsWith(sec.logicalKey)));
      const count = stories.length || sec.count || 0;
      if (!count) return null;
      const isCurrent = currentSection === sec.key || currentSection === sec.logicalKey;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `clean-topic-btn ${isCurrent ? 'active' : ''}`;
      btn.innerHTML = `
        <span class="clean-topic-icon">${getTopicIcon(sec.logicalKey || sec.key)}</span>
        <span>
          <span class="clean-topic-name">${sec.title}</span>
          <span class="clean-topic-count">${isCurrent ? 'Playing now' : `${count} stories`}</span>
        </span>
      `;
      btn.addEventListener('click', () => {
        const firstStory = stories[0];
        if (firstStory) {
          player.seekTo(firstStory.start || 0);
          player.audio.play().catch(() => {});
        }
        $('allStoriesSheet')?.classList.add('hidden');
      });
      return btn;
    }).filter(Boolean));
  }

  // Populate searchable stories list
  const list = $('cleanStoriesList');
  if (list) {
    list.replaceChildren(...b.stories.map((story, i) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'clean-story-item';
      item.dataset.storyId = story.id;
      const isCur = player.current === story.id;
      if (isCur) item.classList.add('current');
      item.innerHTML = `
        <span class="clean-cat-pill" style="font-size:10px;padding:2px 6px;">${(story.section || 'NEWS').toUpperCase()}</span>
        <div class="clean-story-item-text">
          <div class="clean-story-item-title">${i + 1}. ${story.headline || story.title}</div>
          <div class="clean-story-item-sub">${story.source ? story.source.split('·')[0].trim() : 'Daily News'} · ${story.duration ? fmtTime(story.duration) : '20s'}</div>
        </div>
      `;
      item.addEventListener('click', () => {
        player.playChapter(story.id);
        $('allStoriesSheet')?.classList.add('hidden');
      });
      return item;
    }));
  }
}

function filterAllStoriesList(q) {
  const query = (q || '').toLowerCase().trim();
  document.querySelectorAll('#cleanStoriesList .clean-story-item').forEach((item) => {
    const text = item.textContent.toLowerCase();
    item.classList.toggle('hidden', query.length > 0 && !text.includes(query));
  });
}

function openAllStoriesSheet() {
  renderAllStoriesSheet();
  $('allStoriesSheet')?.classList.remove('hidden');
}

/* ------------------------------------------------------------------ events */
function bindEvents() {
  // Clean Player bindings
  deleteAccountSheet = new DeleteAccountSheet();

  $('cleanFormatPodcast')?.addEventListener('click', () => setBriefingMode('podcast'));
  $('cleanFormatFull')?.addEventListener('click', () => setBriefingMode('full'));

  $('openMenuBtn')?.addEventListener('click', () => {
    updateMenuDrawer();
    $('menuDrawer')?.classList.remove('hidden');
  });
  $('closeMenuBtn')?.addEventListener('click', () => $('menuDrawer')?.classList.add('hidden'));
  $('menuDrawer')?.addEventListener('click', (e) => {
    if (e.target === $('menuDrawer')) $('menuDrawer')?.classList.add('hidden');
  });
  $('menuTodayBtn')?.addEventListener('click', () => {
    $('menuDrawer')?.classList.add('hidden');
    $('auxSheet')?.classList.add('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  $('menuFormatBtn')?.addEventListener('click', () => {
    const nextMode = activeMode() === 'podcast' ? 'full' : 'podcast';
    setBriefingMode(nextMode);
    updateMenuDrawer();
  });
  $('menuVoicesBtn')?.addEventListener('click', () => {
    $('menuDrawer')?.classList.add('hidden');
    openAuxSheet('settings');
  });
  $('menuSourcesBtn')?.addEventListener('click', () => {
    $('menuDrawer')?.classList.add('hidden');
    openAuxSheet('sources');
  });
  $('menuRegionBtn')?.addEventListener('click', () => {
    cycleEdition();
    updateMenuDrawer();
  });
  $('menuOfflineBtn')?.addEventListener('click', downloadOfflineAudio);
  $('menuSleepTimerBtn')?.addEventListener('click', cycleSleepTimer);
  $('menuDeleteAccountBtn')?.addEventListener('click', () => {
    $('menuDrawer')?.classList.add('hidden');
    if (deleteAccountSheet) deleteAccountSheet.open(state.profile?.email);
  });
  $('menuAuthBtn')?.addEventListener('click', () => {
    $('menuDrawer')?.classList.add('hidden');
    if (state.profile) {
      sb.auth.signOut();
    } else {
      openSignIn('menu');
    }
  });

  // All Stories Sheet bindings
  $('openAllStoriesBtn')?.addEventListener('click', openAllStoriesSheet);
  $('closeAllStoriesBtn')?.addEventListener('click', () => $('allStoriesSheet')?.classList.add('hidden'));
  $('allStoriesSheet')?.addEventListener('click', (e) => {
    if (e.target === $('allStoriesSheet')) $('allStoriesSheet')?.classList.add('hidden');
  });
  $('cleanStoriesSearch')?.addEventListener('input', (e) => filterAllStoriesList(e.target.value));

  // Aux Sheet bindings
  $('closeAuxBtn')?.addEventListener('click', () => {
    $('auxSheet')?.classList.add('hidden');
    switchTab('today');
  });
  $('auxSheet')?.addEventListener('click', (e) => {
    if (e.target === $('auxSheet')) {
      $('auxSheet')?.classList.add('hidden');
      switchTab('today');
    }
  });
  document.querySelectorAll('#tabbar .tab').forEach((t) => t.addEventListener('click', () => switchTab(t.dataset.tab)));
  $('saveBtn').addEventListener('click', saveAll);
  $('discardBtn').addEventListener('click', discardAll);
  wireSheet($('confirmDialog'));
  $('miniPlayer').addEventListener('click', (e) => {
    if (e.target.closest('button')) return;
    switchTab('today');
  });
  $('installBtn')?.addEventListener('click', install);
  wireSheet($('installSheet'));
  onInstallChange(() => { syncInstallBtn(); renderGuestBanner(); });
  $('topbarSignInBtn')?.addEventListener('click', () => openSignIn('topbar'));
  $('bannerCloseBtn')?.addEventListener('click', () => {
    localStorage.setItem('mb-guest-banner-dismissed', 'true');
    $('guestBanner')?.classList.add('hidden');
  });
  $('bannerSignInBtn')?.addEventListener('click', () => openSignIn('banner'));
  $('bannerInstallBtn')?.addEventListener('click', install);
  $('bannerPushBtn')?.addEventListener('click', bannerSetupPush);
  bindSignInModal();
  $('themeToggle')?.addEventListener('click', () => setTheme(currentTheme() === 'dark' ? 'light' : 'dark'));
  document.addEventListener('mb-theme', syncThemeIcon);
  $('reportSend')?.addEventListener('click', sendReport);
  wireSheet($('reportSheet'));
  const shareSheet = $('shareSheet');
  if (shareSheet) wireSheet(shareSheet);

  // Lineup sheet modal
  const openLineup = () => {
    const sheet = $('lineupSheet');
    if (sheet) {
      if (typeof sheet.showModal === 'function') sheet.showModal();
      else sheet.classList.remove('hidden');
    }
  };
  window.openLineup = openLineup;
  $('openLineupBtn')?.addEventListener('click', openLineup);
  $('readerQueueBtn')?.addEventListener('click', openLineup);
  const lineupSheet = $('lineupSheet');
  if (lineupSheet) wireSheet(lineupSheet);
  $('lineupSearchInput')?.addEventListener('input', (e) => applySearch(e.target.value));

  // Search input & keyboard shortcut
  $('searchInput')?.addEventListener('input', (e) => applySearch(e.target.value));

  // Text size toggles
  document.querySelectorAll('#textSize button').forEach((btn) => {
    btn.addEventListener('click', () => setTextSize(btn.dataset.size));
  });

  // Action buttons
  $('editionSelect')?.addEventListener('change', (e) => setEdition(e.target.value));
  $('modeFullBtn')?.addEventListener('click', () => setBriefingMode('full'));
  $('modeRapidBtn')?.addEventListener('click', () => setBriefingMode('rapid'));
  $('modePodcastBtn')?.addEventListener('click', () => setBriefingMode('podcast'));
  $('reorderBtn')?.addEventListener('click', () => switchTab('sources'));
  $('playAllBtn')?.addEventListener('click', () => {
    player.seekTo(0);
    player.audio.play().catch(() => {});
  });
  const narrSheet = $('narratorSheet');
  if (narrSheet) wireSheet(narrSheet);
  const showPodcastVoiceBanner = () => {
    const banner = $('podcastVoiceBanner');
    if (!banner) return;
    banner.classList.remove('hidden');
    banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  const openNarratorSheet = () => {
    if (activeMode() === 'podcast') {
      showPodcastVoiceBanner();
      return;
    }
    $('podcastVoiceBanner')?.classList.add('hidden');
    renderPersonas();
    narrSheet?.showModal();
  };
  $('narratorChip')?.addEventListener('click', openNarratorSheet);
  $('heroNarratorBtn')?.addEventListener('click', openNarratorSheet);

  $('bannerSwitchFullBtn')?.addEventListener('click', () => {
    $('podcastVoiceBanner')?.classList.add('hidden');
    setBriefingMode('full');
    renderPersonas();
    narrSheet?.showModal();
  });
  $('bannerDismissVoiceBtn')?.addEventListener('click', () => {
    $('podcastVoiceBanner')?.classList.add('hidden');
  });
  $('bannerCloseVoiceBtn')?.addEventListener('click', () => {
    $('podcastVoiceBanner')?.classList.add('hidden');
  });
  $('avatarBtn')?.addEventListener('click', () => switchTab('settings'));

  // Transcript full text / compact view toggle
  const transBox = $('transcript');
  const transExpandBtn = $('transcriptExpandBtn');
  const transExpandLabel = $('transcriptExpandLabel');
  transExpandBtn?.addEventListener('click', () => {
    const isExpanded = transBox?.classList.toggle('expanded');
    transExpandBtn.setAttribute('aria-expanded', String(!!isExpanded));
    if (transExpandLabel) transExpandLabel.textContent = isExpanded ? 'Compact' : 'Full text';
  });

  player.addEventListener('chapter', syncPlaying);
  player.addEventListener('chapter', followChapter);
  player.addEventListener('chapter', syncMini);
  player.addEventListener('chapter', renderAllStoriesSheet);
  player.addEventListener('state', syncPlaying);
  player.addEventListener('state', syncMini);
  // Follow-along stands down for a moment whenever the listener scrolls the page.
  const noteScroll = () => { lastScroll = Date.now(); };
  for (const ev of ['scroll', 'wheel', 'touchstart']) window.addEventListener(ev, noteScroll, { passive: true });

  document.addEventListener('keydown', (e) => {
    if (e.target.closest('input, textarea, select, dialog[open]') || e.metaKey || e.ctrlKey) return;
    if (e.key === '/') {
      e.preventDefault();
      $('searchInput')?.focus();
      return;
    }
    if (e.key === ' ' || e.key === 'k') { e.preventDefault(); player.toggle(); }
    else if (e.key === 'ArrowRight') player.nextChapter();
    else if (e.key === 'ArrowLeft') player.prevChapter();
  });

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') renderHeader();
  });

  // Track clicks on external attribution & creator links (e.g. vattitude.ca in footers and legal sections)
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a');
    if (!link) return;
    const href = link.getAttribute('href') || link.href || '';
    if ((href.includes('vattitude.ca') || href.includes('vattitude.me')) && !href.includes('hark.vattitude.ca')) {
      trackEvent('click_vattitude_footer', {
        link_url: href,
        link_text: (link.textContent || '').trim(),
        location: window.location.pathname || '/',
      });
      trackEvent('click', {
        link_url: href,
        link_domain: 'vattitude.ca',
        outbound: true,
      });
    }
  });
}

/* ----------------------------------------------------------------- sign in modal */
function dismissGuestBannerSoon() {
  localStorage.setItem('mb-guest-banner-dismissed', 'true');
  const pushBtn = $('bannerPushBtn');
  if (pushBtn) {
    const span = pushBtn.querySelector('span');
    if (span) span.textContent = 'Notifications enabled ✓';
    pushBtn.classList.add('glass-btn');
  }
  setTimeout(() => {
    const banner = $('guestBanner');
    if (banner && !banner.classList.contains('hidden')) {
      banner.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      banner.style.opacity = '0';
      banner.style.transform = 'translateY(-8px)';
      setTimeout(() => {
        banner.classList.add('hidden');
        banner.style.removeProperty('transition');
        banner.style.removeProperty('opacity');
        banner.style.removeProperty('transform');
      }, 400);
    }
  }, 2200);
}

async function bannerSetupPush() {
  if (window.HarkNative) {
    if (window.HarkNative.hasNotificationPermission()) {
      toast('Notifications are already active on this device.');
      dismissGuestBannerSoon();
      return;
    }
    try {
      const perm = await requestNotificationPermission();
      if (perm === 'granted' || window.HarkNative.hasNotificationPermission()) {
        toast('Notifications enabled! Daily briefings will alert your phone.');
        try {
          window.HarkNative.postNotification('Hark Daily', 'Daily briefing alerts are now enabled.');
        } catch (_) {}
        dismissGuestBannerSoon();
      } else {
        toast('Notification permission was not granted.', { error: true });
      }
    } catch (err) {
      toast(err.message || "Couldn't set up notifications.", { error: true });
    }
    return;
  }

  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    toast('Notifications are already active on this device.');
    dismissGuestBannerSoon();
    return;
  }
  try {
    const perm = await requestNotificationPermission();
    if (perm === 'granted') {
      toast('Notification permission allowed!');
      dismissGuestBannerSoon();
      if (!state.profile) {
        openSignIn('push');
        toast('Sign in to connect your morning brief dispatch.');
      } else {
        const status = state.status || await api.status().catch(() => ({}));
        if (status?.vapid_public_key) {
          await enablePush(status.vapid_public_key);
          toast('Notifications active! You will be notified when your briefing is ready.');
        }
      }
    } else {
      toast(perm === 'denied' ? 'Notifications are blocked in browser settings.' : 'Permission was not granted.', { error: true });
    }
  } catch (err) {
    toast(err.message || "Couldn't set up notifications.", { error: true });
  }
}

function bindSignInModal() {
  const modal = $('signin');
  if (!modal) return;
  $('signinClose')?.addEventListener('click', closeSignIn);
  modal.addEventListener('click', (e) => { if (e.target.id === 'signin') closeSignIn(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.classList.contains('hidden')) closeSignIn(); });

  const busy = (btn, on, label) => { if (btn) { btn.disabled = on; btn.textContent = label; } };
  const showErr = (msg) => {
    const errEl = $('loginError');
    if (errEl) {
      errEl.textContent = msg || '';
      errEl.classList.toggle('hidden', !msg);
    }
  };

  $('googleBtn')?.addEventListener('click', async () => {
    showErr();
    const btn = $('googleBtn');
    const lbl = $('googleLabel');
    if (btn) btn.disabled = true;
    if (lbl) lbl.textContent = 'Opening Google…';
    try {
      await api.signInWithGoogle();
    } catch (ex) {
      showErr(/provider is not enabled|unsupported provider/i.test(ex.message)
        ? 'Google sign-in is not switched on yet. Use email instead.' : ex.message);
      if (btn) btn.disabled = false;
      if (lbl) lbl.textContent = 'Continue with Google';
    }
  });

  $('useEmail')?.addEventListener('click', () => {
    showErr();
    $('providerStep')?.classList.add('hidden');
    $('emailForm')?.classList.remove('hidden');
    $('loginEmail')?.focus();
  });

  let waitingEmail = '';
  let waitTimer = null;

  $('emailForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    showErr();
    waitingEmail = $('loginEmail')?.value.trim().toLowerCase() || '';
    const btn = $('sendCodeBtn');
    busy(btn, true, 'Sending…');
    try {
      await api.sendCode(waitingEmail);
      $('emailForm')?.classList.add('hidden');
      $('sentStep')?.classList.remove('hidden');
      $('codeForm')?.classList.add('hidden');
      $('signinTitle').textContent = 'Check your email';
      $('loginHint').textContent = `We sent a sign-in link to ${waitingEmail}. Open it on this device to sign in.`;

      clearInterval(waitTimer);
      waitTimer = setInterval(async () => {
        if (await api.session()) {
          clearInterval(waitTimer);
          closeSignIn();
          await enterApp();
        }
      }, 3000);
    } catch (ex) {
      showErr(ex.message);
    } finally {
      busy(btn, false, 'Email me a sign-in link');
    }
  });

  $('resendBtn')?.addEventListener('click', async () => {
    showErr();
    try {
      await api.sendCode(waitingEmail);
      toast('Sent a new link. Please check your inbox.');
    } catch (ex) {
      showErr(ex.message);
    }
  });

  $('showCode')?.addEventListener('click', () => {
    const cf = $('codeForm');
    if (cf) {
      cf.classList.toggle('hidden');
      if (!cf.classList.contains('hidden')) $('loginCode')?.focus();
    }
  });

  $('codeForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    showErr();
    const code = $('loginCode')?.value.trim();
    if (!code) return;
    const btn = $('verifyBtn');
    busy(btn, true, 'Signing in…');
    try {
      await api.verifyCode(waitingEmail, code);
      clearInterval(waitTimer);
      closeSignIn();
      await enterApp();
    } catch (ex) {
      showErr(/expired|invalid/i.test(ex.message) ? 'That code is wrong or has expired.' : ex.message);
    } finally {
      busy(btn, false, 'Sign in with code');
    }
  });

  $('changeEmail')?.addEventListener('click', () => {
    clearInterval(waitTimer);
    showErr();
    $('sentStep')?.classList.add('hidden');
    $('emailForm')?.classList.remove('hidden');
    $('signinTitle').textContent = 'Sign in to Hark Daily';
  });
}

/* ----------------------------------------------------------------- landing */
let landing = null;
let started = false;

async function showLanding() {
  document.body.classList.remove('booting');
  document.body.classList.add('signed-out');
  $('login')?.classList.remove('hidden');
  if (!landing) landing = new Landing({ onSignedIn: enterApp });
  await landing.show();
}

async function enterApp() {
  landing?.stop();
  document.body.classList.remove('booting', 'signed-out');
  $('login')?.classList.add('hidden');
  if (location.hash.includes('access_token')) history.replaceState(null, '', location.pathname);
  if (started) {
    try {
      state.profile = await api.profile();
      const guest = store.get('guest-settings', null);
      if (guest && state.profile) {
        await api.saveSettings(guest);
        store.set('guest-settings', null);
      }
    } catch { /* guest */ }
    syncAdminTab();
    renderHeader();
    renderGuestBanner();
    return;
  }
  started = true;
  await start();
  const voice = store.get('pending-voice', null);
  if (voice && !state.profile?.settings?.voice) {
    try { await api.saveSettings({ voice }); state.profile = await api.profile(); } catch { /* keep default */ }
  }
  store.set('pending-voice', null);
  syncAdminTab();
  const st = state.profile?.settings || {};
  if (state.profile && !st.onboarded && !st.name) welcome.open(state.status);
  else if (state.profile && !st.push_offered && pushSupported() && (window.HarkNative ? !window.HarkNative.hasNotificationPermission() : (typeof Notification !== 'undefined' && Notification.permission === 'default'))) welcome.open(state.status, { askName: false });
}
window.enterApp = enterApp;

/* -------------------------------------------------------------------- boot */
async function start() {
  document.body.classList.remove('booting', 'signed-out');
  const today = new Date().toLocaleDateString('en-CA');
  const urlParams = new URLSearchParams(window.location.search);
  const targetInfo = getTargetStoryInfo();
  const targetDate = targetInfo.date || urlParams.get('date') || today;

  // 1. Instant optimistic paint from cached briefing (0 ms!)
  if (!state.briefing) {
    const cached = store.get('last-briefing', null);
    const canUseCache = cached && (!(targetInfo.date || urlParams.get('date')) || cached.date === targetDate)
      && (!cached.edition || cached.edition === state.edition)
      && (!targetInfo.hash || cached.stories?.some((s) => (s.key && s.key === targetInfo.hash) || storyKey(s) === targetInfo.hash))
      && (!targetInfo.title || cached.stories?.some((s) => titlesMatch(s.headline, targetInfo.title)))
      && (!targetInfo.story || cached.stories?.some((s) => s.id === targetInfo.story || s.key === targetInfo.story));
    if (canUseCache && (cached.stories?.length || cached.clips?.length)) {
      state.briefing = cached;
      state.briefingLoading = false;
      displayBriefing();
    } else {
      state.briefingLoading = true;
      renderNotice();
      renderGuestBanner();
      $('sections').replaceChildren(...Array.from({ length: 3 }, () => h('div', { class: 'skeleton' })));
    }
  }

  try {
    // 2. Fetch status, profile, AND requested date's pack in parallel
    const [status, profile, freshBriefing] = await Promise.all([
      api.status().catch(() => ({})),
      api.profile().catch(() => null),
      loadStoryPack(targetDate)
    ]);
    state.status = status;
    state.profile = profile;
    syncAdminTab();
    applyPhotoMode(profile?.settings?.color_photos);
    renderHeader();
    renderGuestBanner();
    renderPersonas();

    // 3. Fallback to today / latest date if target date is not ready
    let briefing = freshBriefing;
    if (!briefing && targetDate !== today) {
      briefing = await loadStoryPack(today);
    }
    if (!briefing) {
      const latest = await api.latestStoryDate();
      if (latest && latest !== today) {
        briefing = await loadStoryPack(latest);
      }
    }

    state.briefingLoading = false;
    if (briefing) {
      state.briefing = briefing;
      if (state.briefing?.podcastFallback) toast("Podcast isn't ready today, so here's the full brief.");
      displayBriefing();
    }

    // 4. Defer archive loading to background idle time (non-blocking!)
    if ('requestIdleCallback' in window) {
      requestIdleCallback(() => loadArchive().catch(() => {}));
    } else {
      setTimeout(() => loadArchive().catch(() => {}), 150);
    }
  } catch (err) {
    state.briefingLoading = false;
    recordError(err, 'loadBriefing');
    const cached = store.get('last-briefing', null);
    if (cached && (cached.audio_url?.startsWith('http') || cached.stories?.length)) {
      state.briefing = cached;
      displayBriefing();
      toast('Offline mode active. Showing your saved briefing.', { error: true, ms: 5000 });
    } else {
      renderHeader();
      renderNotice();
      renderGuestBanner();
      renderHero();
      renderSections();
      toast("Couldn't reach the briefing service. Please try again shortly.", { error: true, ms: 5000 });
    }
  } finally {
    document.body.classList.remove('booting', 'signed-out');
  }
}

function initConsentPopup() {
  const popup = $('consentPopup');
  if (!popup) return;

  const current = (() => {
    try { return localStorage.getItem('hark-consent'); } catch (e) { return null; }
  })();

  // If already decided, don't show popup
  if (current === 'granted' || current === 'denied') return;

  // Gently reveal after a short delay so page paint is instantaneous
  setTimeout(() => {
    popup.classList.remove('hidden');
    requestAnimationFrame(() => popup.classList.add('show'));
  }, 1200);

  $('consentAccept')?.addEventListener('click', () => {
    try { localStorage.setItem('hark-consent', 'granted'); } catch (e) {}
    window.gtag?.('consent', 'update', { 'analytics_storage': 'granted' });
    popup.classList.remove('show');
    setTimeout(() => popup.classList.add('hidden'), 350);
    toast('Analytics cookies accepted ✓');
  });

  $('consentReject')?.addEventListener('click', () => {
    try { localStorage.setItem('hark-consent', 'denied'); } catch (e) {}
    window.gtag?.('consent', 'update', { 'analytics_storage': 'denied' });
    popup.classList.remove('show');
    setTimeout(() => popup.classList.add('hidden'), 350);
    toast('Analytics cookies rejected');
  });
}

async function handleNativeAuthCallback(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return;
  try {
    let search = '';
    let hash = '';
    const qIdx = rawUrl.indexOf('?');
    const hIdx = rawUrl.indexOf('#');
    if (qIdx !== -1) {
      search = hIdx !== -1 && hIdx > qIdx ? rawUrl.slice(qIdx + 1, hIdx) : rawUrl.slice(qIdx + 1);
    }
    if (hIdx !== -1) {
      hash = rawUrl.slice(hIdx + 1);
    }

    const params = new URLSearchParams(search);
    const hashParams = new URLSearchParams(hash);

    const errorDesc = params.get('error_description') || hashParams.get('error_description')
      || params.get('error') || hashParams.get('error');
    if (errorDesc) {
      toast(errorDesc, { error: true });
      return;
    }

    const code = params.get('code') || hashParams.get('code');
    if (code) {
      toast('Signing you in…');
      const { data, error } = await sb.auth.exchangeCodeForSession(code);
      if (error) {
        console.error('exchangeCodeForSession error:', error);
        toast(error.message || 'Authentication failed. Please try again.', { error: true });
        return;
      }
      if (data?.session) {
        toast('Signed in successfully! 👋');
        $('loginModal')?.classList.add('hidden');
        $('menuDrawer')?.classList.add('hidden');
        setTimeout(enterApp, 0);
        return;
      }
    }

    const accessToken = hashParams.get('access_token') || params.get('access_token');
    const refreshToken = hashParams.get('refresh_token') || params.get('refresh_token');
    if (accessToken && refreshToken) {
      toast('Signing you in…');
      const { data, error } = await sb.auth.setSession({
        access_token: accessToken,
        refresh_token: refreshToken,
      });
      if (error) {
        console.error('setSession error:', error);
        toast(error.message || 'Authentication failed. Please try again.', { error: true });
        return;
      }
      if (data?.session) {
        toast('Signed in successfully! 👋');
        $('loginModal')?.classList.add('hidden');
        $('menuDrawer')?.classList.add('hidden');
        setTimeout(enterApp, 0);
        return;
      }
    }
  } catch (err) {
    console.error('handleNativeAuthCallback error:', err);
    toast(err.message || 'Authentication failed.', { error: true });
  }
}
window.handleNativeAuthCallback = handleNativeAuthCallback;

async function init() {
  window.addEventListener('error', (e) => { recordError(e.error || e.message, 'window.onerror'); });
  window.addEventListener('unhandledrejection', (e) => { recordError(e.reason, 'window.unhandledrejection'); });
  syncThemeIcon();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', syncThemeIcon);
  setTextSize(localStorage.getItem('mb-text-size') || 'md');
  bindEvents();
  syncInstallBtn();
  syncAdminTab();
  syncEditionPicker();

  if (window.HarkNative?.getPendingAuthUri) {
    try {
      const pending = window.HarkNative.getPendingAuthUri();
      if (pending) {
        handleNativeAuthCallback(pending);
      }
    } catch (e) {
      console.warn('Failed to retrieve pending auth uri:', e);
    }
  }
  if (!store.get('edition', null)) {
    detectEditionFromIp().then((ipEd) => {
      if (ipEd && ipEd !== state.edition && !store.get('edition', null)) {
        setEdition(ipEd);
      }
    }).catch(() => {});
  }
  initConsentPopup();
  renderHeader();
  renderNotice();
  renderGuestBanner();
  renderPersonas();
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').then((reg) => {
      reg.update().catch(() => {});
    }).catch(() => {});
  }
  sb.auth.onAuthStateChange(async (event, session) => {
    if (event === 'SIGNED_OUT') {
      started = false;
      state.profile = null;
      syncAdminTab();
      renderHeader();
      renderGuestBanner();
      toast('Signed out. Continuing in guest mode.');
    } else if (session && (event === 'SIGNED_IN' || event === 'INITIAL_SESSION')) {
      setTimeout(enterApp, 0);
    }
  });
  try {
    let session = null;
    try { session = await api.session(); } catch { /* offline */ }
    await enterApp();
  } catch (err) {
    recordError(err, 'app.init');
    await enterApp();
  } finally {
    document.body.classList.remove('booting', 'signed-out');
  }
}

init();
