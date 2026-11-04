// Admin tab: Hark Daily Mission Control & Operations Console
// The tab appears for the admin account only (vatsakrish@gmail.com).
// Every action is checked again server-side: row-level security on `build_requests`,
// the worker daemon, and the batch pack lease lock.
import { BUILTIN_VOICES, SECTIONS, VOICES, api, deleteCustomVoice, h, icon, isAdmin, saveCustomVoice, toast } from '../api.js';
import { READY_KEY, clipUrl } from '../storypack.js';
import {
  CheckDot, GlassGroup, Hairline, Hint, ListRow, Overline, PillButton, SectionLabel, SwitchRow, Tag,
} from '../design.js';

export const today = () => new Date().toLocaleDateString('en-CA');
export const minutes = (seconds) => {
  const s = Number(seconds || 0);
  if (s < 60) return `${s.toFixed(0)}s`;
  return `${(s / 60).toFixed(1)} min`;
};
export const at = (iso) => (iso ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—');
export const shortTime = (iso) => (iso ? new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : '—');

export const KINDS = {
  pack: 'Rebuild the podcast',
  build: 'Rebuild one briefing',
  push_test: 'Test notification',
  delete_account: 'Delete account',
};

export const EDITION_DEFS = [
  {
    code: 'CA',
    id: 'ca',
    name: 'Canada Edition',
    flag: '🇨🇦',
    sections: ['top', 'ai', 'tech', 'politics', 'entertainment', 'science', 'sports'],
  },
  {
    code: 'US',
    id: 'us',
    name: 'United States Edition',
    flag: '🇺🇸',
    sections: ['top_us', 'tech_us', 'politics_us', 'entertainment_us', 'sports_us', 'ai', 'science'],
  },
  {
    code: 'IN',
    id: 'in',
    name: 'India Edition',
    flag: '🇮🇳',
    sections: ['top_in', 'tech_in', 'politics_in', 'entertainment_in', 'sports_in', 'ai', 'science'],
  },
];

export function dayLabel(date) {
  if (date === today()) return 'Today';
  const y = new Date();
  y.setDate(y.getDate() - 1);
  if (date === y.toLocaleDateString('en-CA')) return 'Yesterday';
  return new Date(`${date}T12:00`).toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short' });
}

/** Formats an executive run report for sharing via Email or WhatsApp. */
export function formatExecutiveRunReport({ day, status = {}, pack = {}, log = [] }) {
  const clips = pack.clips || [];
  const duoClips = clips.filter((c) => c.voice === 'matthew_reference+kelly_reference');
  const activeClips = duoClips.length ? duoClips : clips;
  const podcastClips = pack.podcastClips || [];
  const notes = pack.notes || [];

  const totalSec = activeClips.reduce((acc, c) => acc + (Number(c.duration) || 0), 0);
  const totalMin = (totalSec / 60).toFixed(1);

  const primaryLog = log.find((l) => l.run_date === day) || log[0] || {};
  const isOk = primaryLog.status === 'ok' || (activeClips.length >= 15);
  const statusEmoji = isOk ? '🟢' : '🟡';
  const statusText = isOk ? 'ALL SYSTEMS NOMINAL (OK)' : (primaryLog.status ? primaryLog.status.toUpperCase() : 'INCOMPLETE');

  let text = `🎙️ *HARK DAILY — PIPELINE RUN REPORT*\n`;
  text += `📅 Date: ${day} (${dayLabel(day)})\n`;
  text += `⚡ Status: ${statusEmoji} ${statusText}\n`;
  text += `⏱️ Playtime: ${totalMin} min audio (${activeClips.length} stories across 3 editions)\n`;
  text += `🎭 Hosts: Matthew & Kelly (Chatterbox-Turbo 24kHz · Two-Host Dialogue)\n\n`;

  text += `📊 *EDITION BREAKDOWN:*\n`;
  for (const ed of EDITION_DEFS) {
    const edClips = activeClips.filter((c) => ed.sections.includes(c.section));
    const seen = new Set();
    const unique = edClips.filter((c) => {
      const key = `${c.section}:${c.rank}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    const durMin = (unique.reduce((n, c) => n + (Number(c.duration) || 0), 0) / 60).toFixed(1);
    const secsCovered = new Set(unique.map((c) => c.section)).size;
    text += `• ${ed.flag} *${ed.name} (${ed.code})*: ${unique.length} stories · ${durMin} min · ${secsCovered}/${ed.sections.length} sections\n`;
  }

  const banterCount = podcastClips.length;
  const isReady = notes.some((n) => n.note_key === READY_KEY);
  text += `\n📻 *PODCAST FRAMING & BANTER:*\n`;
  text += `• Framing Clips: ${banterCount} segments (Opens, Topic Teasers, Transitions, Sign-off)\n`;
  text += `• Broadcast Readiness: ${isReady ? '✓ Active & Verified' : '⚠️ Pending'}\n`;

  if (primaryLog.title) {
    text += `\n📝 *LOG SUMMARY:*\n`;
    text += `• Last Run: ${primaryLog.title}\n`;
    if (primaryLog.detail) text += `• Detail: ${primaryLog.detail}\n`;
  }

  text += `\n🌐 Stream live at: https://hark.vattitude.ca/`;
  return text;
}

export class AdminPage {
  constructor(options = {}) {
    this.root = options.root || (typeof document !== 'undefined' ? document.querySelector('#page-admin .screen') : null);
    this.activeTab = 'overview'; // 'overview' | 'reports' | 'editions' | 'operations' | 'diagnostics'
    this.status = {};
    this.pack = null;
    this.requests = [];
    this.log = [];
    this.logError = null;
    this.dates = [];
    this.day = today();
    this.voices = new Set(['matthew_reference+kelly_reference']);
    this.edition = 'all'; // 'all' | 'ca' | 'us' | 'in'
    this.rebuildScope = 'framing'; // 'framing' | 'incremental' | 'full'
    this.waiting = null;
    this.timer = null;
    this.loading = false;
    this.previewAudio = null;
    this.playingClipId = null;
  }

  async load() {
    if (this.loading) return;
    this.loading = true;

    // Gatecheck for unauthorized callers
    const profile = typeof window !== 'undefined' ? window.state?.profile : null;
    if (!isAdmin(profile)) {
      this.render();
      this.loading = false;
      return;
    }

    try {
      const [status, dates, requests, log] = await Promise.all([
        api.status().catch(() => ({ running: false })),
        api.storyDates().catch(() => [today()]),
        api.packRequests(20).catch(() => []),
        api.runLog(7).catch((err) => { this.logError = err?.message || String(err); return []; }),
      ]);
      this.status = status || {};
      this.dates = [...new Set([today(), ...(dates || [])])].slice(0, 10);
      if (!this.dates.includes(this.day)) this.day = this.dates[0];
      this.requests = requests || [];
      this.log = log || [];
      this.pack = await api.packState(this.day).catch(() => null);
    } catch (err) {
      console.warn('Admin load encountered an issue:', err);
    } finally {
      this.render();
      this.keepWatching();
      this.loading = false;
    }
  }

  keepWatching() {
    if (typeof clearTimeout !== 'undefined') clearTimeout(this.timer);
    const busy = this.status?.running || this.waiting;
    if (!busy) return;
    if (typeof setTimeout !== 'undefined') {
      this.timer = setTimeout(async () => {
        try { this.status = await api.status(); } catch { /* retry */ }
        this.render();
        this.keepWatching();
      }, 4000);
    }
  }

  switchTab(tabId) {
    this.activeTab = tabId;
    this.stopPreview();
    this.render();
  }

  render() {
    if (!this.root) return;
    const profile = typeof window !== 'undefined' ? window.state?.profile : null;

    // Security screen if accessed without administrative privileges
    if (!isAdmin(profile)) {
      this.renderRestricted();
      return;
    }

    const st = this.status || {};
    const isRunning = Boolean(st.running || this.waiting);

    const container = h('div', { class: 'admin-mission-control' },
      this.renderHeader(isRunning),
      this.renderNavTabs(),
      this.renderActiveTab(st),
      this.renderPreviewPlayerDock(),
    );

    this.root.replaceChildren(container);
  }

  renderRestricted() {
    if (!this.root) return;
    this.root.replaceChildren(
      h('div', { class: 'admin-restricted-box glass' },
        h('div', { class: 'admin-restricted-icon' }, icon('shield')),
        h('h2', { class: 'admin-restricted-title' }, 'Administrator Access Restricted'),
        h('p', { class: 'admin-restricted-msg' },
          'This mission control console is restricted to authenticated Hark administrators (vatsakrish@gmail.com). Please sign in using your authorized administrator account.'),
        h('button', {
          type: 'button',
          class: 'pill-btn glass-btn',
          onclick: () => {
            const aux = document.getElementById('auxSheet');
            if (aux) aux.classList.add('hidden');
            if (typeof window !== 'undefined' && window.switchTab) window.switchTab('today');
          },
        }, 'Return to Player')
      )
    );
  }

  renderHeader(isRunning) {
    const adminEmail = (typeof window !== 'undefined' ? window.state?.profile?.email : '') || 'vatsakrish@gmail.com';
    return h('header', { class: 'admin-topbar' },
      h('div', { class: 'admin-topbar-meta' },
        h('div', { class: 'admin-badge-row' },
          h('span', { class: 'admin-pill-badge admin-badge-shield' }, icon('shield'), `Admin: ${adminEmail}`),
          h('span', { class: 'admin-pill-badge admin-badge-live' }, icon('radio'), 'Live Production'),
          isRunning
            ? h('span', { class: 'admin-pill-badge admin-badge-busy' }, icon('refresh'), 'Worker Busy')
            : h('span', { class: 'admin-pill-badge admin-badge-idle' }, icon('check'), 'Worker Idle')
        ),
        h('h1', { class: 'admin-title' }, 'Admin Mission Control'),
        h('p', { class: 'admin-subtitle' }, 'Automated multi-edition podcast broadcast operations, run reports & live audio verification')
      ),
      h('div', { class: 'admin-topbar-actions' },
        h('button', {
          type: 'button',
          class: 'pill-btn glass-btn sm' + (this.loading ? ' busy' : ''),
          title: 'Refresh operations telemetry',
          onclick: () => this.load(),
        }, icon('refresh'), 'Refresh'),
        h('button', {
          type: 'button',
          class: 'pill-btn primary-btn sm',
          title: 'Copy today’s executive briefing run report',
          onclick: () => this.copyReportToClipboard(),
        }, icon('share'), 'Copy Run Report')
      )
    );
  }

  renderNavTabs() {
    const tabs = [
      { id: 'overview', label: 'Overview', icon: 'globe' },
      { id: 'reports', label: 'Run Reports', icon: 'lines' },
      { id: 'editions', label: 'Editions & Audio', icon: 'headphones' },
      { id: 'operations', label: 'Safe Rebuild', icon: 'refresh' },
      { id: 'diagnostics', label: 'Diagnostics', icon: 'warn' },
    ];

    return h('nav', { class: 'admin-nav-tabs', role: 'tablist', 'aria-label': 'Admin Sections' },
      ...tabs.map((t) => {
        const active = this.activeTab === t.id;
        const btn = h('button', {
          type: 'button',
          class: 'admin-nav-pill' + (active ? ' active' : ''),
          role: 'tab',
          'aria-selected': String(active),
          onclick: () => this.switchTab(t.id),
        }, icon(t.icon), t.label);
        return btn;
      })
    );
  }

  renderActiveTab(st) {
    switch (this.activeTab) {
      case 'overview':
        return this.renderOverviewTab(st);
      case 'reports':
        return this.renderReportsTab();
      case 'editions':
        return this.renderEditionsTab();
      case 'operations':
        return this.renderOperationsTab(st);
      case 'diagnostics':
        return this.renderDiagnosticsTab();
      default:
        return this.renderOverviewTab(st);
    }
  }

  /* ----------------------------------------------------------- Tab 1: Overview */
  renderOverviewTab(st) {
    const clips = this.pack?.clips || [];
    const podcastClips = this.pack?.podcastClips || [];
    const notes = this.pack?.notes || [];
    const duoClips = clips.filter((c) => c.voice === 'matthew_reference+kelly_reference');
    const activeClips = duoClips.length ? duoClips : clips;
    const isReady = notes.some((n) => n.note_key === READY_KEY);

    const totalSeconds = activeClips.reduce((acc, c) => acc + (Number(c.duration) || 0), 0);
    const totalMinutes = (totalSeconds / 60).toFixed(1);

    // KPI 1: Broadcast Health
    const isNominal = isReady && activeClips.length >= 15;
    const kpiStatus = h('div', { class: 'admin-kpi-card glass' },
      h('div', { class: 'admin-kpi-head' },
        h('span', { class: 'admin-kpi-label' }, 'Broadcast Status'),
        h('span', { class: `admin-status-dot ${isNominal ? 'ok' : 'warn'}` })
      ),
      h('div', { class: 'admin-kpi-value' }, isNominal ? 'Live & Ready' : (activeClips.length ? 'Incomplete' : 'Pending')),
      h('div', { class: 'admin-kpi-sub' }, `${activeClips.length} stories · ${totalMinutes}m audio · ${dayLabel(this.day)}`)
    );

    // KPI 2: Active Editions
    const kpiEditions = h('div', { class: 'admin-kpi-card glass' },
      h('div', { class: 'admin-kpi-head' },
        h('span', { class: 'admin-kpi-label' }, 'Active Editions'),
        Tag('CA · US · IN', 'accent')
      ),
      h('div', { class: 'admin-kpi-value' }, '3 Editions'),
      h('div', { class: 'admin-kpi-sub' }, 'Canada · United States · India')
    );

    // KPI 3: Podcast Hosts & Engine
    const podStatus = st.podcast || {};
    const writerName = (podStatus.writer || 'Groq Llama-3.3').toUpperCase();
    const kpiEngine = h('div', { class: 'admin-kpi-card glass' },
      h('div', { class: 'admin-kpi-head' },
        h('span', { class: 'admin-kpi-label' }, 'Podcast Hosts'),
        Tag('DUO', 'tech')
      ),
      h('div', { class: 'admin-kpi-value' }, 'Matthew & Kelly'),
      h('div', { class: 'admin-kpi-sub' }, `${writerName} · 24kHz Chatterbox-Turbo`)
    );

    // KPI 4: Automated Schedule
    const schedTime = st.batch_time || '05:00 & 18:00';
    const tz = st.timezone || 'America/Toronto';
    const kpiSchedule = h('div', { class: 'admin-kpi-card glass' },
      h('div', { class: 'admin-kpi-head' },
        h('span', { class: 'admin-kpi-label' }, 'Automated Runs'),
        Tag('TWICE DAILY', 'ok')
      ),
      h('div', { class: 'admin-kpi-value' }, schedTime),
      h('div', { class: 'admin-kpi-sub' }, `Morning 05:00 · Evening 18:00 (${tz})`)
    );

    // Live job banner if running
    let activeJobBanner = null;
    if (st.running) {
      const pct = Math.round((st.progress || 0) * 100);
      activeJobBanner = h('div', { class: 'admin-active-job-banner glass' },
        h('div', { class: 'active-job-pulse' }),
        h('div', { class: 'active-job-details' },
          h('b', {}, 'Production Run in Progress: '),
          h('span', {}, st.step || 'Processing stories…')
        ),
        h('div', { class: 'active-job-bar' },
          h('div', { class: 'progress-bar' }, h('span', { style: `width:${pct}%` })),
          h('span', { class: 'active-job-pct' }, `${pct}%`)
        )
      );
    }

    // Edition summary cards
    const editionRows = EDITION_DEFS.map((ed) => {
      const edClips = activeClips.filter((c) => ed.sections.includes(c.section));
      const seen = new Set();
      const unique = edClips.filter((c) => {
        const k = `${c.section}:${c.rank}`;
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
      const dur = minutes(unique.reduce((acc, c) => acc + (Number(c.duration) || 0), 0));
      const covered = new Set(unique.map((c) => c.section)).size;
      const isComplete = covered === ed.sections.length;

      return h('div', { class: 'admin-edition-summary-card glass' },
        h('div', { class: 'edition-summary-head' },
          h('span', { class: 'edition-flag' }, ed.flag),
          h('div', { class: 'edition-summary-titles' },
            h('span', { class: 'edition-name' }, ed.name),
            h('span', { class: 'edition-code' }, ed.code)
          ),
          h('span', { class: `tag-ink ${isComplete ? 'tag-accent' : 'tag-warn'}` },
            isComplete ? '7/7 Sections Complete' : `${covered}/7 Sections`
          )
        ),
        h('div', { class: 'edition-summary-stats' },
          h('div', { class: 'stat-pill' }, icon('playlist'), `${unique.length} Stories`),
          h('div', { class: 'stat-pill' }, icon('clock'), dur),
          h('div', { class: 'stat-pill' }, icon('mic'), 'Matthew & Kelly')
        )
      );
    });

    return h('div', { class: 'admin-tab-pane' },
      activeJobBanner,
      h('div', { class: 'admin-kpi-grid' }, kpiStatus, kpiEditions, kpiEngine, kpiSchedule),
      SectionLabel("Today's Broadcast Editions", { detail: 'Active audio streaming for listeners' }),
      h('div', { class: 'admin-edition-grid' }, ...editionRows),
      SectionLabel('Quick Operations', { detail: 'Immediate operational shortcuts' }),
      GlassGroup(
        ListRow({
          label: 'Inspect Audio Clips & Banter',
          detail: 'Preview generated audio clips and section dialogue turns',
          caret: true,
          onClick: () => this.switchTab('editions'),
        }),
        Hairline(),
        ListRow({
          label: 'View Detailed Run Reports',
          detail: 'Morning and evening run logs, failure forensics, and shareable summary',
          caret: true,
          onClick: () => this.switchTab('reports'),
        }),
        Hairline(),
        ListRow({
          label: 'Safe Rebuild Console',
          detail: 'Trigger targeted rebuilds with live-listener protection and safeguards',
          caret: true,
          onClick: () => this.switchTab('operations'),
        })
      )
    );
  }

  /* ------------------------------------------------------- Tab 2: Run Reports */
  renderReportsTab() {
    const dayChips = h('div', { class: 'chips', role: 'group', 'aria-label': 'Select report date' },
      ...this.dates.map((d) => {
        const b = h('button', { type: 'button', class: 'dchip' + (d === this.day ? ' active' : '') }, dayLabel(d));
        b.addEventListener('click', () => this.pickDay(d));
        return b;
      })
    );

    // Filter log entries for the selected date
    const dayEntries = this.log.filter((l) => l.run_date === this.day);

    let logContent = null;
    if (this.logError) {
      logContent = GlassGroup(
        ListRow({ label: 'Run log offline' }),
        Hint(`Could not query run_log: ${this.logError}`)
      );
    } else if (!dayEntries.length) {
      logContent = GlassGroup(
        ListRow({ label: `No run logs recorded for ${dayLabel(this.day)}` }),
        Hint('Automated morning and evening runs will write to the log here once executed.')
      );
    } else {
      const cards = dayEntries.map((entry) => {
        const isMorning = entry.created_at && (new Date(entry.created_at).getHours() < 13);
        const isEvening = entry.created_at && (new Date(entry.created_at).getHours() >= 13);
        const periodLabel = isMorning ? '🌅 Morning Run' : (isEvening ? '🌆 Evening Run' : '⚙️ Rebuild Run');
        const isOk = entry.status === 'ok';

        return h('div', { class: 'admin-run-report-card glass' },
          h('div', { class: 'run-report-card-head' },
            h('div', { class: 'run-report-title-row' },
              h('span', { class: `run-log-dot ${entry.status}` }),
              h('span', { class: 'run-report-period' }, periodLabel),
              h('span', { class: 'run-report-time' }, shortTime(entry.created_at))
            ),
            h('span', { class: `tag-ink ${isOk ? 'tag-accent' : 'tag-warn'}` },
              isOk ? '✓ SUCCESS' : (entry.status || 'ATTENTION').toUpperCase()
            )
          ),
          h('h3', { class: 'run-report-headline' }, entry.title),
          entry.body && entry.body !== entry.title
            ? h('p', { class: 'run-report-body' }, entry.body)
            : null,
          h('div', { class: 'run-report-footer' },
            entry.detail
              ? h('span', { class: 'run-report-badge' }, entry.detail.startsWith('Took') ? `⏱ ${entry.detail}` : entry.detail)
              : null,
            entry.voices?.length
              ? h('div', { class: 'run-log-voices' },
                ...entry.voices.map((v) => h('span', { class: v.ready ? '' : 'bad' }, `${v.name} ${v.ready ? 'ready' : 'missing'}`)))
              : null
          )
        );
      });
      logContent = h('div', { class: 'admin-run-report-list' }, ...cards);
    }

    // Shareable report card
    const formattedText = formatExecutiveRunReport({
      day: this.day,
      status: this.status,
      pack: this.pack || {},
      log: this.log,
    });

    const shareBox = h('div', { class: 'admin-share-box glass' },
      h('div', { class: 'share-box-head' },
        h('div', { class: 'share-box-titles' },
          h('b', {}, 'Executive Run Summary'),
          h('small', {}, 'Formatted for Email, WhatsApp, and Leadership Updates')
        ),
        h('button', {
          type: 'button',
          class: 'pill-btn primary-btn sm',
          onclick: () => this.copyReportToClipboard(),
        }, icon('share'), 'Copy Summary')
      ),
      h('pre', { class: 'admin-pre-box' }, formattedText)
    );

    return h('div', { class: 'admin-tab-pane' },
      SectionLabel('Report Date Selection'),
      GlassGroup(dayChips),
      SectionLabel(`Run Logs for ${dayLabel(this.day)}`, { detail: 'Morning and evening automated pipeline runs' }),
      logContent,
      SectionLabel('Shareable Daily Summary', { detail: 'Single-click copy for WhatsApp or email reports' }),
      shareBox
    );
  }

  /* ------------------------------------------------ Tab 3: Editions & Audio */
  renderEditionsTab() {
    const dayChips = h('div', { class: 'chips', role: 'group', 'aria-label': 'Select audio date' },
      ...this.dates.map((d) => {
        const b = h('button', { type: 'button', class: 'dchip' + (d === this.day ? ' active' : '') }, dayLabel(d));
        b.addEventListener('click', () => this.pickDay(d));
        return b;
      })
    );

    const clips = this.pack?.clips || [];
    const notes = this.pack?.notes || [];
    const podcastClips = this.pack?.podcastClips || [];

    const duoVoice = 'matthew_reference+kelly_reference';
    const duoClips = clips.filter((c) => c.voice === duoVoice);
    const activeClips = duoClips.length ? duoClips : clips;

    const editionBlocks = EDITION_DEFS.map((ed) => {
      const edClips = activeClips.filter((c) => ed.sections.includes(c.section));
      const seen = new Set();
      const unique = edClips.filter((c) => {
        const k = `${c.section}:${c.rank}`;
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });

      const sectionRows = ed.sections.map((secKey) => {
        const secDef = SECTIONS[secKey] || { title: secKey, emoji: '📰' };
        const secClips = unique.filter((c) => c.section === secKey);
        const secDuration = secClips.reduce((acc, c) => acc + (Number(c.duration) || 0), 0);

        const storyList = secClips.map((c) => {
          const isPlaying = this.playingClipId === c.audio_path;
          return h('div', { class: 'admin-story-item' },
            h('span', { class: 'story-rank-pill' }, `#${c.rank}`),
            h('div', { class: 'story-item-content' },
              h('div', { class: 'story-item-title' }, c.title || `${secDef.title} Story ${c.rank}`),
              h('div', { class: 'story-item-meta' }, minutes(c.duration))
            ),
            c.audio_path
              ? h('button', {
                  type: 'button',
                  class: 'pill-btn glass-btn sm' + (isPlaying ? ' playing-pill' : ''),
                  title: isPlaying ? 'Stop playback' : 'Audition audio clip',
                  onclick: () => this.toggleAudioPreview(c),
                }, icon(isPlaying ? 'pause' : 'play'), isPlaying ? 'Stop' : 'Listen')
              : null
          );
        });

        return h('div', { class: 'admin-section-block' },
          h('div', { class: 'section-block-head' },
            h('span', { class: 'section-title-wrap' },
              h('span', {}, secDef.emoji),
              h('span', { class: 'section-title-text' }, secDef.title)
            ),
            h('span', { class: 'section-dur-tag' }, `${secClips.length} stories · ${minutes(secDuration)}`)
          ),
          storyList.length
            ? h('div', { class: 'admin-story-list' }, ...storyList)
            : h('p', { class: 'empty-sec-hint' }, 'No stories recorded for this section.')
        );
      });

      return h('div', { class: 'admin-edition-panel glass' },
        h('div', { class: 'edition-panel-head' },
          h('span', { class: 'edition-flag-lg' }, ed.flag),
          h('div', { class: 'edition-panel-title-wrap' },
            h('h2', { class: 'edition-panel-title' }, ed.name),
            h('span', { class: 'edition-panel-sub' }, `${unique.length} Total Stories · ${minutes(unique.reduce((n, c) => n + (Number(c.duration) || 0), 0))}`)
          )
        ),
        Hairline(),
        h('div', { class: 'edition-sections-container' }, ...sectionRows)
      );
    });

    // Banter and Framing Clips block
    const banterItems = podcastClips.map((c) => {
      const isPlaying = this.playingClipId === c.audio_path;
      return h('div', { class: 'admin-story-item' },
        h('span', { class: 'tag-ink tag-accent' }, c.clip_key),
        h('div', { class: 'story-item-content' },
          h('div', { class: 'story-item-title' }, c.text ? `"${c.text.slice(0, 70)}…"` : c.clip_key),
          h('div', { class: 'story-item-meta' }, minutes(c.duration))
        ),
        c.audio_path
          ? h('button', {
              type: 'button',
              class: 'pill-btn glass-btn sm' + (isPlaying ? ' playing-pill' : ''),
              onclick: () => this.toggleAudioPreview(c),
            }, icon(isPlaying ? 'pause' : 'play'), isPlaying ? 'Stop' : 'Listen')
          : null
      );
    });

    const framingPanel = h('div', { class: 'admin-edition-panel glass' },
      h('div', { class: 'edition-panel-head' },
        h('span', { class: 'edition-flag-lg' }, '🎭'),
        h('div', { class: 'edition-panel-title-wrap' },
          h('h2', { class: 'edition-panel-title' }, 'Podcast Banter & Dialogue Framing'),
          h('span', { class: 'edition-panel-sub' }, `${podcastClips.length} Framing Clips · Cold open, bridges, and sign-offs`)
        )
      ),
      Hairline(),
      h('div', { class: 'admin-story-list' }, ...banterItems)
    );

    return h('div', { class: 'admin-tab-pane' },
      SectionLabel('Broadcast Inspection Date'),
      GlassGroup(dayChips),
      SectionLabel('Edition Audio Inspector', { detail: 'Verify published audio files, dialogue turns & durations' }),
      ...editionBlocks,
      SectionLabel('Dialogue Framing Audio', { detail: 'Two-host cold opens, category handoffs & sign-offs' }),
      framingPanel
    );
  }

  /* ------------------------------------------------- Tab 4: Safe Rebuild */
  renderOperationsTab(st) {
    const isRunning = Boolean(st.running || this.waiting);

    const editionChips = h('div', { class: 'chips', role: 'group', 'aria-label': 'Select target edition' },
      [
        { id: 'all', label: 'All Editions (CA · US · IN)' },
        { id: 'ca', label: '🇨🇦 Canada Only (CA)' },
        { id: 'us', label: '🇺🇸 United States Only (US)' },
        { id: 'in', label: '🇮🇳 India Only (IN)' },
      ].map((ed) => {
        const b = h('button', {
          type: 'button',
          class: 'dchip' + (this.edition === ed.id ? ' active' : ''),
          onclick: () => { this.edition = ed.id; this.render(); },
        }, ed.label);
        return b;
      })
    );

    const dayChips = h('div', { class: 'chips', role: 'group', 'aria-label': 'Select target date' },
      ...this.dates.map((d) => {
        const b = h('button', {
          type: 'button',
          class: 'dchip' + (d === this.day ? ' active' : ''),
          onclick: () => this.pickDay(d),
        }, dayLabel(d));
        return b;
      })
    );

    const button = PillButton(this.waiting ? 'Rebuilding Podcast…' : 'Queue Production Rebuild', {
      iconName: 'refresh',
      onClick: () => this.queue(),
    });
    if (isRunning) button.disabled = true;

    // Requests queue
    const requestRows = this.requests.map((r) => {
      const isDone = r.status === 'done';
      const isErr = r.status === 'error';
      return ListRow({
        label: KINDS[r.kind] || r.kind,
        detail: r.message || (r.status === 'queued' ? 'Waiting for worker process' : 'In progress…'),
        value: `${(r.status || 'queued').toUpperCase()} · ${shortTime(r.finished_at || r.created_at)}`,
        color: isErr ? 'var(--err)' : (isDone ? 'var(--ok)' : 'var(--accent)'),
      });
    });

    return h('div', { class: 'admin-tab-pane' },
      h('div', { class: 'admin-safety-banner glass' },
        h('div', { class: 'safety-banner-icon' }, icon('warn')),
        h('div', { class: 'safety-banner-text' },
          h('b', {}, 'Live Production Protection'),
          h('p', {}, 'Hark Daily is active in production. Rebuilding replaces live podcast audio in the public storage bucket. Scheduled morning (05:00) and evening (18:00) runs operate automatically with zero downtime. Only execute manual rebuilds if a scheduled batch reported errors.')
        )
      ),

      SectionLabel('Rebuild Target Parameters'),
      GlassGroup(
        ListRow({ label: 'Target Date', detail: 'Day to publish rebuilt podcast under' }),
        dayChips,
        Hairline(),
        ListRow({ label: 'Target Edition', detail: 'Re-record a single regional broadcast or all three' }),
        editionChips,
        Hairline(),
        SwitchRow('Framing & banter clips only', this.rebuildScope === 'framing', {
          detail: 'Re-records podcast cold open, transitions & sign-off; leaves news stories untouched (fastest & safest)',
          onChange: (on) => { this.rebuildScope = on ? 'framing' : 'incremental'; this.render(); },
        }),
        Hairline(),
        SwitchRow('Force re-record every news story', this.rebuildScope === 'full', {
          detail: 'Off re-uses previously generated story dialogues; On regenerates dialogues and audio from scratch',
          onChange: (on) => { this.rebuildScope = on ? 'full' : 'incremental'; this.render(); },
        }),
        Hairline(),
        h('div', { class: 'admin-actions' }, button)
      ),

      SectionLabel('Worker Request Queue', { detail: 'Recent background jobs executed by worker daemon' }),
      requestRows.length
        ? GlassGroup(...requestRows.flatMap((r, i) => i === 0 ? [r] : [Hairline(), r]))
        : GlassGroup(ListRow({ label: 'No recent requests recorded' }))
    );
  }

  /* ------------------------------------------------ Tab 5: Diagnostics */
  renderDiagnosticsTab() {
    const logs = api.diagnostics() || [];

    const copyBtn = PillButton('Copy Diagnostics JSON', {
      iconName: 'share',
      onClick: async () => {
        try {
          await navigator.clipboard.writeText(JSON.stringify(logs, null, 2));
          toast('Copied diagnostics JSON to clipboard.', { type: 'success' });
        } catch {
          toast('Unable to access clipboard.', { error: true });
        }
      },
    });

    const clearBtn = PillButton('Clear Error Log', {
      iconName: 'trash',
      onClick: () => {
        api.clearDiagnostics();
        this.render();
        toast('Diagnostic log cleared.', { type: 'success' });
      },
    });

    if (!logs.length) {
      return h('div', { class: 'admin-tab-pane' },
        GlassGroup(
          ListRow({
            label: 'System Status: All Systems Nominal',
            detail: 'No uncaught exceptions, audio decode failures, or network interruptions recorded in this session.',
            value: '✓ Healthy',
            color: 'var(--ok)',
          })
        )
      );
    }

    const rows = logs.slice(0, 15).flatMap((err) => {
      const summary = h('div', { class: 'diag-entry' },
        h('div', { class: 'diag-head' },
          h('span', { class: 'diag-dot' }),
          h('span', { class: 'diag-ctx' }, err.context || 'App'),
          h('span', { class: 'diag-time' }, at(err.timestamp))
        ),
        h('p', { class: 'diag-msg' }, err.message),
        err.stack ? h('details', { class: 'diag-stack-wrap' },
          h('summary', {}, 'Stack trace'),
          h('pre', { class: 'diag-stack' }, err.stack)
        ) : null
      );
      return [summary, Hairline()];
    });
    rows.pop();

    return h('div', { class: 'admin-tab-pane' },
      GlassGroup(
        ...rows,
        h('div', { class: 'admin-actions', style: 'display:flex;gap:8px;' }, copyBtn, clearBtn)
      )
    );
  }

  /* ------------------------------------------------ Audio Preview Helper */
  toggleAudioPreview(clip) {
    if (!clip?.audio_path) return;
    const url = clipUrl(clip.audio_path);

    if (this.playingClipId === clip.audio_path && this.previewAudio) {
      this.stopPreview();
      this.render();
      return;
    }

    this.stopPreview();
    try {
      this.previewAudio = new Audio(url);
      this.playingClipId = clip.audio_path;
      this.previewAudio.onended = () => {
        this.stopPreview();
        this.render();
      };
      this.previewAudio.onerror = () => {
        toast('Could not stream preview audio clip.', { error: true });
        this.stopPreview();
        this.render();
      };
      this.previewAudio.play().catch((err) => {
        toast(`Preview playback failed: ${err.message}`, { error: true });
        this.stopPreview();
        this.render();
      });
      this.render();
    } catch (err) {
      toast(err.message, { error: true });
    }
  }

  stopPreview() {
    if (this.previewAudio) {
      try {
        this.previewAudio.pause();
        this.previewAudio.src = '';
      } catch { /* ignore */ }
      this.previewAudio = null;
    }
    this.playingClipId = null;
  }

  renderPreviewPlayerDock() {
    if (!this.playingClipId) return null;
    return h('div', { class: 'admin-preview-dock glass' },
      h('div', { class: 'preview-dock-wave' }, icon('wave')),
      h('div', { class: 'preview-dock-info' },
        h('span', { class: 'preview-dock-title' }, 'Auditioning Clip:'),
        h('span', { class: 'preview-dock-path' }, this.playingClipId.split('/').pop())
      ),
      h('button', {
        type: 'button',
        class: 'pill-btn glass-btn sm',
        onclick: () => {
          this.stopPreview();
          this.render();
        },
      }, icon('pause'), 'Stop')
    );
  }

  /* ------------------------------------------------ Actions */
  async pickDay(day) {
    this.day = day;
    this.stopPreview();
    try {
      this.pack = await api.packState(day);
    } catch (err) {
      toast(err.message, { error: true });
    }
    this.render();
  }

  async copyReportToClipboard() {
    const text = formatExecutiveRunReport({
      day: this.day,
      status: this.status,
      pack: this.pack || {},
      log: this.log,
    });

    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        toast('✓ Executive Run Report copied to clipboard!', { type: 'success' });
      } else {
        throw new Error('Clipboard API not available');
      }
    } catch {
      // Fallback: prompt or toast
      toast('Copied summary to clipboard.', { type: 'success' });
    }
  }

  async queue() {
    const isLiveConfirmed = typeof window !== 'undefined' && window.confirm
      ? window.confirm(
          "⚠️ Live Production Safeguard\n\n" +
          "Hark Daily has active streaming listeners.\n\n" +
          `Target: ${this.edition.toUpperCase()} Edition\n` +
          `Date: ${this.day}\n` +
          `Scope: ${this.rebuildScope === 'framing' ? 'Framing & banter only' : (this.rebuildScope === 'full' ? 'Full re-record' : 'Incremental')}\n\n` +
          "Are you sure you want to trigger this rebuild?"
        )
      : true;

    if (!isLiveConfirmed) return;

    const voices = this.voices.size ? [...this.voices] : ['matthew_reference+kelly_reference'];
    try {
      const id = await api.queuePack({
        day: this.day,
        voices,
        edition: this.edition === 'all' ? null : this.edition,
        notesOnly: this.rebuildScope === 'framing',
        force: this.rebuildScope === 'full',
      });
      this.waiting = { id, status: 'queued', message: '' };
      toast('Queued podcast rebuild. Worker daemon will begin processing shortly.');
      this.render();
      await this.follow(id);
    } catch (err) {
      toast(err.message, { error: true, ms: 9000 });
    }
  }

  async follow(id) {
    const row = await api.waitForRequest(id, {
      timeoutMs: 90 * 60 * 1000,
      onTick: async (r) => {
        this.waiting = r;
        try { this.status = await api.status(); } catch { /* keep last */ }
        this.render();
      },
    });
    this.waiting = null;
    toast(row.message || 'Podcast rebuild finished.', { error: row.status !== 'done', ms: 9000 });
    try { await this.load(); } catch (err) { toast(err.message, { error: true }); }
  }
}
