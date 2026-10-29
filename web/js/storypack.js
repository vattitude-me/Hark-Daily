// The shared daily story pack, mirrored from app/storypack.py.
//
// The worker voices each day's stories once and publishes them as clips in Supabase
// Storage. This module picks the clips a given listener asked for and lays them out
// on one timeline, so the player can play them back to back with no server-side merge.
import { SECTIONS, voiceName } from './api.js';
import { SUPABASE_URL } from '../config.js';

export const LOGICAL_SECTIONS = ['top', 'ai', 'tech', 'politics', 'entertainment', 'science', 'sports'];
export const SECTION_ORDER = LOGICAL_SECTIONS;
export const MAX_PER_SECTION = 5;

export function editionSectionKey(logicalKey, edition = 'ca') {
  if (['ai', 'tech', 'science'].includes(logicalKey)) return logicalKey;
  if (edition === 'us') return `${logicalKey}_us`;
  if (edition === 'in') return `${logicalKey}_in`;
  return logicalKey;
}

/** The per-section story counts a user asked for (0 = off), clamped to 0..MAX. Defaults to MAX_PER_SECTION. */
export function lineup(settings) {
  const chosen = (settings && settings.stories) || {};
  const out = {};
  for (const key of SECTION_ORDER) {
    const raw = chosen[key];
    const n = raw !== undefined ? Number.parseInt(raw, 10) : MAX_PER_SECTION;
    out[key] = Number.isFinite(n) ? Math.max(0, Math.min(n, MAX_PER_SECTION)) : MAX_PER_SECTION;
  }
  return out;
}

/** The public Storage URL for a clip's object path. */
export function clipUrl(path) {
  return `${SUPABASE_URL}/storage/v1/object/public/briefings/${path}`;
}

const CONNECTORS = [
  'Here are the details:', "Here's what you need to know:", 'Taking a closer look:',
  "Here's what's happening:", 'According to the reporting:', 'In the details:', 'Behind the headline:',
];

const LABEL_PREFIX = /^(?:the news|why it matters|what to know|what happened|the big picture|from the source|between the lines|catch up quick|by the numbers|what they(?:'re| are) saying|what's next|the backstory|yes, but|details|context|zoom in|zoom out|what to watch|state of play):\s*/i;

/**
 * Clean headline matcher: returns true if two titles match, ignoring punctuation, case,
 * or minor publisher word variations using Dice word similarity (threshold >= 0.65).
 */
export function titlesMatch(a, b) {
  if (!a || !b) return false;
  const clean = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, ' ').replace(/\s+/g, ' ').trim();
  const ca = clean(a);
  const cb = clean(b);
  if (!ca || !cb) return false;
  if (ca === cb) return true;
  if (ca.startsWith(cb) || cb.startsWith(ca)) return true;
  const wordsA = ca.split(' ').filter((w) => w.length > 2);
  const wordsB = cb.split(' ').filter((w) => w.length > 2);
  if (!wordsA.length || !wordsB.length) return false;
  const setB = new Set(wordsB);
  const common = wordsA.filter((w) => setB.has(w)).length;
  const similarity = (2 * common) / (wordsA.length + wordsB.length);
  return similarity >= 0.65;
}

/**
 * Extract clean body summary from broadcast script by stripping repeated headline,
 * podcast banter connectors, and editorial section prefixes (e.g. "The news:").
 */
export function stripHeadlineAndFiller(headline, scriptOrSummary) {
  let text = (scriptOrSummary || '').trim();
  if (!text) return '';
  const cleanTitle = (headline || '').trim().replace(/[.!?:]+$/, '');
  if (cleanTitle) {
    const esc = cleanTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    text = text.replace(new RegExp('^' + esc + '[.!?]?\\s*', 'i'), '').trim();
  }
  const connPattern = new RegExp('^(?:' + CONNECTORS.map((c) => c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')\\s*', 'i');
  text = text.replace(connPattern, '').trim();
  text = text.replace(LABEL_PREFIX, '').trim();
  if (text && text[0] === text[0].toLowerCase()) {
    text = text[0].toUpperCase() + text.slice(1);
  }
  return text || scriptOrSummary;
}

/**
 * Which voice's clips to play: the one this listener picked, or — when that recording isn't
 * published (a render that failed, or a voice they used to have) — whichever one is there.
 */
export function pickVoice(rows, chosen) {
  const ids = (rows || []).map((r) => r.voice).filter(Boolean);
  if (!ids.length) return null;
  if (chosen && ids.includes(chosen)) return chosen;
  const counts = new Map();
  for (const id of ids) counts.set(id, (counts.get(id) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
}

/** Order one listener's clips: their voice, then section order, then rank. */
export function clipsFor(rows, wanted, voice, sectionOrder = SECTION_ORDER, edition = 'ca') {
  const bySection = new Map();
  for (const row of rows || []) {
    if (voice && row.voice !== voice) continue;
    if (!bySection.has(row.section)) bySection.set(row.section, []);
    bySection.get(row.section).push(row);
  }
  const ordered = [];
  const order = (Array.isArray(sectionOrder) && sectionOrder.length)
    ? [...sectionOrder.filter((k) => SECTION_ORDER.includes(k)), ...SECTION_ORDER.filter((k) => !sectionOrder.includes(k))]
    : SECTION_ORDER;
  for (const key of order) {
    const count = wanted[key] || 0;
    if (count <= 0) continue;
    const edKey = editionSectionKey(key, edition);
    const pool = bySection.has(edKey) && bySection.get(edKey).length ? bySection.get(edKey) : (bySection.get(key) || []);
    const picked = pool.slice().sort((a, b) => (a.rank || 0) - (b.rank || 0)).slice(0, count);
    ordered.push(...picked);
  }
  return ordered;
}

const round = (n) => Math.round(n * 100) / 100;

/**
 * A breath between two clips, in seconds. Without it the end of one story runs into the start of
 * the next and the two read as a single sentence. It is a real silent clip rather than a delay in
 * the player, so the timeline stays true: story times, seeking and the total all count it.
 */
export const BREATH = 0.8;
const GAP_URL = '/audio/gap.mp3';

/**
 * The marker note a narrator's day carries once every clip and every spoken note is published
 * (app/storypack.py). A day without it is still being recorded, so its audio must not be played.
 */
export const READY_KEY = 'pack_ready';

/** Which greeting to open with, by the listener's local hour (mirrors app/storypack.py). */
export function greetingKey(hour = new Date().getHours()) {
  if (hour < 12) return 'greeting_morning';
  if (hour < 17) return 'greeting_afternoon';
  return 'greeting_evening';
}

/** The marker clip a host pair's day carries once its banter is published (app/podcast.py). */
export const PODCAST_READY_KEY = 'podcast_ready';
/** Total banter, in seconds, a podcast brief may add around the news: the news is the priority. */
export const PODCAST_BUDGET = 90;
/** Sections that get a teaser, so a six-section lineup doesn't open with a minute of chat. */
const MAX_TEASERS = 3;

function stableHash(text) {
  let n = 0;
  for (let i = 0; i < text.length; i += 1) n = (n * 31 + text.charCodeAt(i)) >>> 0;
  return n;
}

/**
 * Choose the banter for one listener's lineup, or null when the day has no usable podcast.
 *
 * `clips` are the day's podcast_clips rows. A day is usable only if a host pair published its ready
 * marker and has an opening and a closing. After those, teasers (first sections first) and then
 * section bridges are added while they fit the budget, so 3 categories get a short chat and 7 do
 * not get a long one. Missing pieces are simply skipped: banter is never required for the news.
 */
export function planPodcast(clips, sections, seed = '') {
  const rows = clips || [];
  const hosts = rows.filter((c) => c.clip_key === PODCAST_READY_KEY).map((c) => c.hosts).sort()[0];
  if (!hosts) return null;
  const mine = rows.filter((c) => c.hosts === hosts && c.clip_key !== PODCAST_READY_KEY && c.audio_path);
  const byKey = new Map(mine.map((c) => [c.clip_key, c]));
  const variant = (kind) => {
    const all = mine.filter((c) => c.clip_key.startsWith(`pod_${kind}_`)).sort((a, b) => a.clip_key.localeCompare(b.clip_key));
    return all.length ? all[stableHash(`${seed}:${kind}`) % all.length] : null;
  };
  const open = variant('open');
  const close = variant('close');
  if (!open || !close) return null;
  const length = (c) => Number(c.duration) || 0;
  let used = length(open) + length(close);
  const teasers = [];
  for (const key of sections.slice(0, MAX_TEASERS)) {
    const baseKey = key.replace(/_(us|in|ca)$/, '');
    const c = byKey.get(`pod_tease_${key}`) || byKey.get(`pod_tease_${baseKey}`);
    if (c && used + length(c) <= PODCAST_BUDGET) { teasers.push(c); used += length(c); }
  }
  const bridges = new Map();
  for (const key of sections) {
    const baseKey = key.replace(/_(us|in|ca)$/, '');
    const c = byKey.get(`pod_bridge_${key}`) || byKey.get(`pod_bridge_${baseKey}`);
    if (c && used + length(c) <= PODCAST_BUDGET) { bridges.set(key, c); used += length(c); }
  }
  return { hosts, open, teasers, bridges, close, banter: used };
}

export function banterTitle(clipKey, sectionKey = null) {
  if (!clipKey) return "Today's Briefing";
  if (clipKey.startsWith('pod_open')) {
    return "Welcome · Today's preview";
  }
  if (clipKey.startsWith('pod_tease')) {
    const sec = sectionKey || clipKey.replace(/^pod_tease_/, '');
    const secName = SECTIONS[sec]?.title || SECTIONS[sec.replace(/_(us|in|ca)$/, '')]?.title || sec;
    return `Coming up · ${secName}`;
  }
  if (clipKey.startsWith('pod_bridge')) {
    const sec = sectionKey || clipKey.replace(/^pod_bridge_/, '');
    const secName = SECTIONS[sec]?.title || SECTIONS[sec.replace(/_(us|in|ca)$/, '')]?.title || sec;
    return `Up next · ${secName}`;
  }
  if (clipKey.startsWith('pod_close')) {
    return "That's today's briefing · Signing off";
  }
  return "Today's Briefing";
}

export function noteTitle(noteKey) {
  if (!noteKey) return "Today's Briefing";
  if (noteKey.startsWith('greeting_morning')) return 'Good morning · Daily briefing';
  if (noteKey.startsWith('greeting_afternoon')) return 'Good afternoon · Daily briefing';
  if (noteKey.startsWith('greeting_evening')) return 'Good evening · Daily briefing';
  if (noteKey.startsWith('intro_')) {
    const sec = noteKey.replace(/^intro_/, '');
    const secName = SECTIONS[sec]?.title || sec;
    return `Here are the ${secName.toLowerCase()} stories`;
  }
  if (noteKey === 'outro') return "That's today's brief";
  return "Today's Briefing";
}

/**
 * Turn the day's shared rows into a briefing the existing UI and player understand.
 *
 * `notes` are the pre-voiced greeting and section intros: the greeting opens the brief
 * (picked from the clock) and each section's line plays before its first story, so it
 * reads like a programme rather than a playlist. Notes become clusters on the same
 * timeline, so they are seekable and never overlap a story.
 *
 * In `podcast` mode the two hosts' banter pieces (`podcastClips`) replace the greeting, section intros
 * and sign-off. If the day has no usable podcast, the result is the normal full brief with
 * `podcastFallback: true` so the UI can say so.
 *
 * Returns `null` when the listener's lineup selects nothing (or the day has no pack).
 */
export function buildBriefing(rows, settings, {
  date, voice, notes = [], hour, mode = 'full', podcastClips = [],
  targetStory = null, targetTitle = null, targetAudio = null, targetSource = null, targetDur = 20,
  edition = 'ca',
} = {}) {
  const isRapid = mode === 'rapid';
  const id = pickVoice(rows, voice);
  const userOrder = (settings && Array.isArray(settings.section_order) && settings.section_order.length)
    ? settings.section_order
    : SECTION_ORDER;
  const order = [...userOrder.filter((k) => SECTION_ORDER.includes(k)), ...SECTION_ORDER.filter((k) => !userOrder.includes(k))];

  // In Rapid Fire mode, select the 5 top stories of the day
  let wanted = lineup(settings);

  // If a specific story is requested via deep link:
  // 1. Try matching by headline title first (resilient against morning/evening batch rank shifts)
  let targetSec = null;
  let targetRank = null;
  let matchedRow = null;

  if (targetTitle) {
    matchedRow = (rows || []).find((r) => (!id || r.voice === id) && titlesMatch(r.title, targetTitle))
      || (rows || []).find((r) => titlesMatch(r.title, targetTitle));
  }

  if (matchedRow) {
    // Found the story in the active pack! Use its actual current section and rank
    targetSec = matchedRow.section;
    targetRank = matchedRow.rank;
  } else if (targetStory) {
    const parts = String(targetStory).split('-');
    if (parts.length >= 2) {
      targetSec = parts[0];
      targetRank = Number.parseInt(parts[parts.length - 1], 10);
    }
  }

  if (targetSec && SECTION_ORDER.includes(targetSec) && Number.isFinite(targetRank) && targetRank > 0) {
    wanted[targetSec] = Math.max(wanted[targetSec] || 0, Math.min(targetRank, MAX_PER_SECTION));
  }

  if (isRapid) {
    const rapidWanted = {};
    for (const key of SECTION_ORDER) rapidWanted[key] = 0;

    // Check available clips for voice in 'top'
    const topClips = (rows || []).filter((r) => (!id || r.voice === id) && r.section === 'top');
    const topCount = Math.min(5, topClips.length);
    rapidWanted['top'] = topCount;

    // If 'top' has fewer than 5 clips, backfill from subsequent sections in user order
    let remaining = 5 - topCount;
    if (remaining > 0) {
      for (const key of order) {
        if (key === 'top') continue;
        const avail = (rows || []).filter((r) => (!id || r.voice === id) && r.section === key).length;
        const take = Math.min(remaining, avail);
        if (take > 0) {
          rapidWanted[key] = take;
          remaining -= take;
        }
        if (remaining <= 0) break;
      }
    }
    // Safeguard: if rows check yielded 0, request 5 from top
    if (!Object.values(rapidWanted).some((v) => v > 0)) {
      rapidWanted['top'] = 5;
    }
    // If a targetStory was deep-linked in rapid mode, make sure its section is also included
    if (targetSec && targetRank && SECTION_ORDER.includes(targetSec)) {
      rapidWanted[targetSec] = Math.max(rapidWanted[targetSec] || 0, Math.min(targetRank, MAX_PER_SECTION));
    }
    wanted = rapidWanted;
  }

  const chosen = clipsFor(rows, wanted, id, order, edition);
  if (!chosen.length && !targetAudio) return null;

  // Resilient deep-link check:
  // 1. If matchedRow was found in rows but was not in chosen, insert it
  if (matchedRow && !chosen.some((r) => r === matchedRow || (r.section === matchedRow.section && r.rank === matchedRow.rank))) {
    chosen.push(matchedRow);
    chosen.sort((a, b) => {
      const secA = order.indexOf(a.section);
      const secB = order.indexOf(b.section);
      if (secA !== secB) return (secA === -1 ? 999 : secA) - (secB === -1 ? 999 : secB);
      return (a.rank || 0) - (b.rank || 0);
    });
  } else if (targetStory && !matchedRow) {
    const hasTarget = chosen.some((r) => `${r.section}-${r.rank}` === targetStory || r.id === targetStory);
    if (!hasTarget) {
      const match = (rows || []).find((r) =>
        (!id || r.voice === id) && (`${r.section}-${r.rank}` === targetStory || r.id === targetStory)
      ) || (rows || []).find((r) => `${r.section}-${r.rank}` === targetStory || r.id === targetStory);
      if (match) {
        chosen.push(match);
        chosen.sort((a, b) => {
          const secA = order.indexOf(a.section);
          const secB = order.indexOf(b.section);
          if (secA !== secB) return (secA === -1 ? 999 : secA) - (secB === -1 ? 999 : secB);
          return (a.rank || 0) - (b.rank || 0);
        });
      }
    }
  }

  // 2. If the story was voiced in an earlier batch (e.g. morning) and replaced in the evening batch,
  // the audio file remains permanent in Supabase Storage. Inject it as a shared story!
  if (targetAudio && !chosen.some((r) => (targetTitle && titlesMatch(r.title, targetTitle)) || r.audio_path === targetAudio)) {
    const sec = (targetSec && SECTION_ORDER.includes(targetSec)) ? targetSec : 'top';
    const cleanHash = targetAudio.replace(/[^a-zA-Z0-9]/g, '').slice(-8);
    const archivedId = targetStory || `shared-${sec}-${cleanHash}`;
    const syntheticRow = {
      section: sec,
      rank: 0,
      title: targetTitle || 'Shared Story',
      summary: targetTitle || 'Shared Story',
      source: targetSource || 'The news',
      url: null,
      image: null,
      duration: targetDur || 20,
      audio_path: targetAudio,
      isSharedBonus: true,
      syntheticId: archivedId,
    };
    chosen.unshift(syntheticRow);
    chosen.sort((a, b) => {
      const secA = order.indexOf(a.section);
      const secB = order.indexOf(b.section);
      if (secA !== secB) return (secA === -1 ? 999 : secA) - (secB === -1 ? 999 : secB);
      return (a.rank || 0) - (b.rank || 0);
    });
  }

  const byKey = new Map(
    (notes || []).filter((n) => !id || n.voice === id).map((n) => [n.note_key, n]),
  );

  const chosenSections = new Set(chosen.map((r) => r.section));
  const targetSections = order.map((key) => {
    const edKey = editionSectionKey(key, edition);
    return chosenSections.has(edKey) ? edKey : (chosenSections.has(key) ? key : null);
  }).filter(Boolean);

  const pod = mode === 'podcast'
    ? planPodcast(podcastClips, targetSections.filter((key) => chosen.some((r) => (r.section === key || r.section === editionSectionKey(key, edition)) && r.rank === 1)),
      `${date}:${id || ''}`)
    : null;
  const isPodcast = Boolean(pod);

  const clips = [];
  const stories = [];
  const chapters = [];
  const counts = new Map();
  let cursor = 0;

  /** A silent clip between two voiced ones, so a story never starts on the last word. */
  const breath = () => {
    if (!cursor) return;
    const start = round(cursor);
    const end = round(cursor + BREATH);
    clips.push({ id: `gap-${clips.length}`, url: GAP_URL, duration: BREATH, section: null, rank: 0,
      title: '', start, end, gap: true });
    cursor += BREATH;
  };

  const sayNote = (key) => {
    const note = byKey.get(key);
    if (!note) return;
    breath();
    const duration = Number(note.duration) || 0;
    const start = round(cursor);
    const end = round(cursor + duration);
    const title = noteTitle(key);
    clips.push({ id: key, url: clipUrl(note.audio_path), duration, section: null, rank: 0,
      title, text: note.text, start, end, note: true });
    chapters.push({ id: key, kind: 'note', title, text: note.text, start, end });
    cursor += duration;
  };

  /** A banter clip from the podcast hosts, placed on the timeline like a note. */
  const sayBanter = (clip, sectionKey = null) => {
    if (!clip) return;
    breath();
    const duration = Number(clip.duration) || 0;
    const start = round(cursor);
    const end = round(cursor + duration);
    const title = banterTitle(clip.clip_key, sectionKey);
    clips.push({ id: clip.clip_key, url: clipUrl(clip.audio_path), duration, section: sectionKey, rank: 0,
      title, text: clip.text, start, end, note: true, banter: true });
    chapters.push({ id: clip.clip_key, kind: 'note', title, text: clip.text, start, end, section: sectionKey });
    cursor += duration;
  };

  if (isPodcast) {
    sayBanter(pod.open);
    pod.teasers.forEach((t) => sayBanter(t));
  } else {
    sayNote(greetingKey(hour));
  }

  let currentSection = null;
  const podHosts = isPodcast ? (pod.hosts || '').split('+').filter(Boolean) : [];
  let storyIndex = 0;
  for (const row of chosen) {
    // In rapid mode, skip section intros to deliver a swift, continuous headline flow
    if (!isRapid && row.section !== currentSection) {
      const baseSec = (row.section || '').replace(/_(us|in|ca)$/, '');
      if (isPodcast) sayBanter(pod.bridges.get(row.section) || pod.bridges.get(baseSec), row.section);
      else sayNote(byKey.has(`intro_${row.section}`) ? `intro_${row.section}` : `intro_${baseSec}`);
      currentSection = row.section;
    }
    breath();
    // In podcast mode, alternate the stories between the two hosts so they co-anchor
    let storyRow = row;
    if (isPodcast && podHosts.length > 1) {
      const targetVoice = podHosts[storyIndex % podHosts.length];
      const match = (rows || []).find((r) => r.section === row.section && r.rank === row.rank && r.voice === targetVoice);
      if (match) storyRow = match;
      storyIndex++;
    }
    const duration = Number(storyRow.duration) || 0;
    const start = round(cursor);
    const end = round(cursor + duration);
    const id = storyRow.syntheticId || `${storyRow.section}-${storyRow.rank}`;
    stories.push({
      id, section: storyRow.section, source: storyRow.source || 'The Guardian',
      headline: storyRow.title,
      summary: storyRow.summary || stripHeadlineAndFiller(storyRow.title, storyRow.script || ''),
      url: storyRow.url || null,
      image: storyRow.image || null, start, end, rapid: isRapid,
      audio_path: storyRow.audio_path,
      isSharedBonus: Boolean(storyRow.isSharedBonus),
    });
    chapters.push({ id, kind: 'story', title: storyRow.title, start, end, section: storyRow.section });
    clips.push({
      id, url: clipUrl(storyRow.audio_path), duration, section: storyRow.section, rank: storyRow.rank,
      title: storyRow.title, start, end,
    });
    counts.set(storyRow.section, (counts.get(storyRow.section) || 0) + 1);
    cursor += duration;
  }

  // The sign-off, after a breath, so the brief does not stop dead on the last story.
  if (isPodcast) sayBanter(pod.close);
  else sayNote('outro');

  const sections = order
    .map((key) => {
      const edKey = editionSectionKey(key, edition);
      const actualKey = counts.has(edKey) ? edKey : (counts.has(key) ? key : null);
      if (!actualKey) return null;
      return {
        key: actualKey,
        logicalKey: key,
        title: (SECTIONS[actualKey] || SECTIONS[key] || {}).title || key,
        count: counts.get(actualKey),
      };
    })
    .filter(Boolean);

  const seenSecKeys = new Set(sections.map((s) => s.key));
  for (const [secKey, count] of counts.entries()) {
    if (!seenSecKeys.has(secKey)) {
      sections.push({
        key: secKey,
        logicalKey: secKey.replace(/_(us|in|ca)$/, ''),
        title: (SECTIONS[secKey] || {}).title || secKey,
        count,
      });
      seenSecKeys.add(secKey);
    }
  }

  const availableVoices = [...new Set((rows || []).map((r) => r.voice).filter(Boolean))];

  return {
    date,
    title: isRapid ? 'Rapid Fire · Top 5 Stories' : isPodcast ? 'Your briefing · Podcast' : 'Your briefing',
    mode: isRapid ? 'rapid' : isPodcast ? 'podcast' : 'full',
    podcastFallback: mode === 'podcast' && !isPodcast,
    duration: round(cursor),
    generated_at: new Date().toISOString(),
    voice: {
      id: isPodcast && podHosts.length ? podHosts.join('+') : id,
      name: isPodcast && podHosts.length ? podHosts.map((h) => voiceName(h)).join(' & ') : voiceName(id),
      requested: voice || null,
      isFallback: Boolean(voice && id !== voice),
    },
    availableVoices,
    writer: 'cbc',
    weather: null,
    sections, chapters, stories, clips,
    notes: [],
  };
}
