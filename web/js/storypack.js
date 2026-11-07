// The shared daily story pack, mirrored from app/storypack.py.
//
// The worker voices each day's stories once and publishes them as clips in Supabase
// Storage. This module picks the clips a given listener asked for and lays them out
// on one timeline, so the player can play them back to back with no server-side merge.
import { SECTIONS, voiceName } from './api.js';
import { SUPABASE_URL } from '../config.js';

export const LOGICAL_SECTIONS = ['top', 'markets', 'ai', 'tech', 'politics', 'entertainment', 'science', 'sports'];
export const SECTION_ORDER = LOGICAL_SECTIONS;
export const MAX_PER_SECTION = 5;

export function editionSectionKey(logicalKey, edition = 'ca') {
  if (['ai', 'science'].includes(logicalKey)) return logicalKey;
  if (edition === 'us') return `${logicalKey}_us`;
  if (edition === 'in') return `${logicalKey}_in`;
  return logicalKey;
}

export const DEFAULT_SECTION_COUNTS = {
  top: 5,
  markets: 3,
  ai: 3,
  tech: 3,
  politics: 3,
  entertainment: 3,
  science: 3,
  sports: 3,
};

export function defaultStoriesForSection(key) {
  return DEFAULT_SECTION_COUNTS[key] ?? (key === 'top' ? 5 : 3);
}

/** The per-section story counts a user asked for (0 = off), clamped to 0..MAX. Defaults: top=5, others=3. */
export function lineup(settings) {
  const chosen = (settings && settings.stories) || {};
  const out = {};
  for (const key of SECTION_ORDER) {
    const raw = chosen[key];
    const n = raw !== undefined ? Number.parseInt(raw, 10) : defaultStoriesForSection(key);
    out[key] = Number.isFinite(n) ? Math.max(0, Math.min(n, MAX_PER_SECTION)) : defaultStoriesForSection(key);
  }
  return out;
}

/** The public Storage URL for a clip's object path. */
export function clipUrl(path) {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  const cleanPath = path.replace(/matthew_reference_kelly_reference/g, 'matthew_reference__kelly_reference');
  return `${SUPABASE_URL}/storage/v1/object/public/briefings/${cleanPath}`;
}

const CONNECTORS = [
  'Here are the details.', "Here's what you need to know.", 'Taking a closer look.',
  "Here's what's happening.", 'According to the reporting.', 'In the details.', 'Behind the headline.',
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
 * Normalize textual shorthand ($5B, 15%, Q3, etc.) into speakable natural words.
 */
export function voiceNormalize(text) {
  if (!text || typeof text !== 'string') return '';
  let s = text;
  // Currencies: $5B -> 5 billion dollars, €10M -> 10 million euros, $25 -> 25 dollars
  s = s.replace(/(?:\b(C|CA|CAD|US|USD|U\.S\.))?(\$|€|£|₹)\s?(\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*(thousand|million|billion|trillion|crore|lakh)\b|\s*(bn|mn|tn|[kmbt])\b)?/gi, (match, prefix, sym, amount, scaleWord, scaleAbbr) => {
    const scaleMap = { k: 'thousand', m: 'million', mn: 'million', b: 'billion', bn: 'billion', t: 'trillion', tn: 'trillion', cr: 'crore', lakh: 'lakh' };
    const scale = scaleWord ? scaleWord.toLowerCase() : (scaleAbbr ? scaleMap[scaleAbbr.toLowerCase()] || '' : '');
    const isSingular = amount === '1' && !scale;
    let curr = 'dollars';
    if (sym === '€') curr = isSingular ? 'euro' : 'euros';
    else if (sym === '£') curr = isSingular ? 'pound' : 'pounds';
    else if (sym === '₹') curr = isSingular ? 'rupee' : 'rupees';
    else if (prefix && /^(C|CA|CAD)$/i.test(prefix)) curr = isSingular ? 'Canadian dollar' : 'Canadian dollars';
    else if (prefix && /^(US|USD|U\.S\.)$/i.test(prefix)) curr = isSingular ? 'U.S. dollar' : 'U.S. dollars';
    else curr = isSingular ? 'dollar' : 'dollars';
    return [amount, scale, curr].filter(Boolean).join(' ');
  });
  // Standalone metric scales: 32B -> 32 billion
  s = s.replace(/\b(\d+(?:\.\d+)?)\s*b\b(?!\w)/gi, '$1 billion');
  s = s.replace(/\b(\d+(?:\.\d+)?)\s*m\b(?!\w)/gi, '$1 million');
  s = s.replace(/\b(\d+(?:\.\d+)?)\s*k\b(?!m|g|w|hz|\w)/gi, '$1 thousand');
  // Percentages: 15% -> 15 percent
  s = s.replace(/(\d+(?:\.\d+)?)\s*%/g, '$1 percent');
  // Quarters: Q3 -> the third quarter
  const quarters = { '1': 'the first quarter', '2': 'the second quarter', '3': 'the third quarter', '4': 'the fourth quarter' };
  s = s.replace(/\bQ([1-4])\b/g, (_, q) => quarters[q] || `quarter ${q}`);
  // Multipliers: 5x -> 5 times
  s = s.replace(/\b(\d+(?:\.\d+)?)x\b/gi, '$1 times');
  // Common symbols & abbreviations
  s = s.replace(/\bvs\.?\b/gi, 'versus');
  s = s.replace(/\bw\/(?=\s|$)/gi, 'with');
  s = s.replace(/\bw\/o(?=\s|$)/gi, 'without');
  s = s.replace(/\b&\b/g, 'and');
  // Strip bracketed speech reaction tags from teleprompter / display text
  s = s.replace(/\[(laugh|chuckle|sigh|gasp|cough|groan|sniffle|yawn)\]/gi, '');
  return s.replace(/\s+/g, ' ').trim();
}

/**
 * Parse speaker-labeled podcast dialogue lines (`[Matthew] ...` / `[Kelly] ...`).
 * Returns an array of `{ speaker, text }` objects when dialogue turns are present, or `null` otherwise.
 */
export function parseDialogueTurns(scriptText) {
  if (!scriptText || typeof scriptText !== 'string') return null;
  const lines = scriptText.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return null;
  const turns = [];
  const turnRe = /^\[([A-Za-z][A-Za-z0-9 &._-]{1,24})\]\s+(.+)$/;
  for (const line of lines) {
    const m = line.match(turnRe);
    if (m) {
      turns.push({ speaker: m[1].trim(), text: voiceNormalize(m[2].trim()) });
    } else if (turns.length) {
      turns[turns.length - 1].text += ` ${voiceNormalize(line)}`;
    }
  }
  return turns.length ? turns : null;
}

/**
 * Extract clean body summary from broadcast script by stripping repeated headline,
 * speaker tags (`[Matthew]`, `[Kelly]`), podcast banter connectors, and editorial prefixes.
 */
export function stripHeadlineAndFiller(headline, scriptOrSummary) {
  let text = (scriptOrSummary || '').trim();
  if (!text) return '';
  text = text.replace(/^\[[A-Za-z][A-Za-z0-9 &._-]{1,24}\]\s*/gm, ' ').replace(/\s+/g, ' ').trim();
  const cleanTitle = (headline || '').trim().replace(/[.!?:]+$/, '');
  if (cleanTitle) {
    const esc = cleanTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    text = text.replace(new RegExp('^' + esc + '[.!?]?\\s*', 'i'), '').trim();
  }
  const connPattern = new RegExp('^(?:' + CONNECTORS.map((c) => c.replace(/[.:]+$/, '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')[.:…—]?\\s*', 'i');
  text = text.replace(connPattern, '').trim();
  text = text.replace(LABEL_PREFIX, '').trim();
  if (text && text[0] === text[0].toLowerCase()) {
    text = text[0].toUpperCase() + text.slice(1);
  }
  return voiceNormalize(text || scriptOrSummary);
}

/**
 * Which voice's clips to play: the one this listener picked, or — when that recording isn't
 * published (a render that failed, or a voice they used to have) — whichever one is there.
 */
export function pickVoice(rows, chosen) {
  const ids = (rows || []).map((r) => r.voice).filter(Boolean);
  if (!ids.length) return null;
  if (chosen && ids.includes(chosen)) return chosen;
  if (ids.includes('matthew_reference+kelly_reference')) return 'matthew_reference+kelly_reference';
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
    const pool = bySection.has(edKey) && bySection.get(edKey).length
      ? bySection.get(edKey)
      : (edition === 'ca' ? (bySection.get(key) || []) : []);
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
 * Unique, region-agnostic 8-character reference key for a story.
 * Prefers the 8-hex-char content hash embedded at the end of `audio_path`
 * (e.g. `stories/2026-10-31/ai-4-matthew_reference__kelly_reference-c80758f3.mp3` -> `c80758f3`),
 * falling back to a deterministic 8-hex-char hash of the story's URL/title.
 */
export function storyKey(row) {
  if (!row) return '';
  if (row.key) return String(row.key).toLowerCase();
  const audio = row.audio_path || '';
  const m = audio.match(/-([0-9a-f]{8})\.mp3$/i);
  if (m) return m[1].toLowerCase();
  const seed = `${row.url || ''}|${row.title || row.headline || ''}|${row.section || ''}-${row.rank || ''}`;
  return stableHash(seed).toString(16).padStart(8, '0').slice(0, 8);
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

  // 1. Regional opener teaser for the very first section (e.g. US/India/Canada top stories)
  // Instead of playing multiple consecutive teasers at the start, only this single regional tease plays
  // before jumping directly into the top stories.
  const firstSec = (sections || [])[0];
  const baseFirstSec = firstSec ? firstSec.replace(/_(us|in|ca)$/, '') : '';
  let regionalTease = (firstSec ? (byKey.get(`pod_tease_${firstSec}`) || byKey.get(`pod_tease_${baseFirstSec}`)) : null) || null;
  if (regionalTease && used + length(regionalTease) <= PODCAST_BUDGET) {
    used += length(regionalTease);
  } else {
    regionalTease = null;
  }
  const teasers = regionalTease ? [regionalTease] : [];

  const bridges = new Map();
  for (const key of (sections || [])) {
    const baseKey = key.replace(/_(us|in|ca)$/, '');
    const c = byKey.get(`pod_bridge_${key}`) || byKey.get(`pod_bridge_${baseKey}`);
    if (c && used + length(c) <= PODCAST_BUDGET) {
      bridges.set(key, c);
      used += length(c);
    }
  }
  return { hosts, open, regionalTease, teasers, bridges, close, banter: used };
}

export function banterTitle(clipKey, sectionKey = null) {
  if (!clipKey) return "Today's Briefing";
  if (clipKey.startsWith('pod_open')) {
    return "Welcome · Today's preview";
  }
  if (clipKey.startsWith('pod_tease')) {
    const sec = sectionKey || clipKey.replace(/^pod_tease_/, '');
    let secName = SECTIONS[sec]?.title || SECTIONS[sec.replace(/_(us|in|ca)$/, '')]?.title || sec;
    if (sec === 'top_us') secName = 'US Top stories';
    else if (sec === 'top_in') secName = 'India Top stories';
    else if (sec === 'top' || sec === 'top_ca') secName = 'Canada Top stories';
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
  targetHash = null, targetImage = null, targetScript = null,
  edition = 'ca',
} = {}) {
  const isRapid = mode === 'rapid';
  const podVoice = (podcastClips || []).find((c) => c.clip_key === PODCAST_READY_KEY)?.hosts || 'matthew_reference+kelly_reference';
  const effectiveVoice = mode === 'podcast' ? podVoice : voice;
  const id = pickVoice(rows, effectiveVoice);
  let order;
  if (settings && Array.isArray(settings.section_order) && settings.section_order.length) {
    const userOrder = settings.section_order.filter((k) => SECTION_ORDER.includes(k));
    const missing = SECTION_ORDER.filter((k) => !userOrder.includes(k));
    if (missing.includes('markets') && userOrder.includes('top')) {
      const topIdx = userOrder.indexOf('top');
      userOrder.splice(topIdx + 1, 0, 'markets');
      const otherMissing = missing.filter((k) => k !== 'markets');
      order = [...userOrder, ...otherMissing];
    } else {
      order = [...userOrder, ...missing];
    }
  } else {
    order = SECTION_ORDER;
  }

  // In Rapid Fire mode, select the 5 top stories of the day
  let wanted = lineup(settings);

  // Normalize targetStory if it is a pure 8-char key ("c80758f3") or includes a trailing hash ("ai-4-c80758f3")
  let normalizedTargetStory = targetStory ? String(targetStory).trim() : null;
  let effectiveHash = targetHash ? String(targetHash).trim().toLowerCase() : null;
  const normAudio = (p) => (p || '').replace(/matthew_reference_kelly_reference/g, 'matthew_reference__kelly_reference');

  if (!effectiveHash && targetAudio) {
    const audioHashMatch = targetAudio.match(/-([0-9a-f]{8})\.mp3$/i);
    if (audioHashMatch) effectiveHash = audioHashMatch[1].toLowerCase();
  }
  if (normalizedTargetStory) {
    if (/^[0-9a-f]{8}$/i.test(normalizedTargetStory)) {
      if (!effectiveHash) effectiveHash = normalizedTargetStory.toLowerCase();
      normalizedTargetStory = null;
    } else {
      const hashMatch = normalizedTargetStory.match(/^([a-z0-9_]+-\d+)-([0-9a-f]{8})$/i);
      if (hashMatch) {
        normalizedTargetStory = hashMatch[1];
        if (!effectiveHash) effectiveHash = hashMatch[2].toLowerCase();
      }
    }
  }

  // If a specific story is requested via deep link:
  // 1. Try matching by unique 8-char story key first (region-agnostic reference key /s/:date/:key)
  // 2. Try matching by headline title next (resilient against morning/evening batch rank shifts)
  // 3. Try matching by normalized audio path (handles dropped/archived morning clips)
  let targetSec = null;
  let targetRank = null;
  let matchedRow = null;

  if (effectiveHash) {
    matchedRow = (rows || []).find((r) => r.voice === 'matthew_reference+kelly_reference' && storyKey(r) === effectiveHash)
      || (rows || []).find((r) => r.script && r.script.includes('[') && storyKey(r) === effectiveHash)
      || (rows || []).find((r) => (!id || r.voice === id) && storyKey(r) === effectiveHash)
      || (rows || []).find((r) => storyKey(r) === effectiveHash);
  }

  if (!matchedRow && targetTitle) {
    matchedRow = (rows || []).find((r) => r.voice === 'matthew_reference+kelly_reference' && titlesMatch(r.title, targetTitle))
      || (rows || []).find((r) => r.script && r.script.includes('[') && titlesMatch(r.title, targetTitle))
      || (rows || []).find((r) => (!id || r.voice === id) && titlesMatch(r.title, targetTitle))
      || (rows || []).find((r) => titlesMatch(r.title, targetTitle));
  }

  if (!matchedRow && targetAudio) {
    const targetClean = normAudio(targetAudio);
    matchedRow = (rows || []).find((r) => r.voice === 'matthew_reference+kelly_reference' && normAudio(r.audio_path) === targetClean)
      || (rows || []).find((r) => normAudio(r.audio_path) === targetClean);
  }

  if (matchedRow) {
    // Found the story in the active pack! Use its actual current section and rank
    targetSec = matchedRow.section;
    targetRank = matchedRow.rank;
  } else if (normalizedTargetStory) {
    const parts = String(normalizedTargetStory).split('-');
    if (parts.length >= 2) {
      targetSec = parts.slice(0, -1).join('-');
      targetRank = Number.parseInt(parts[parts.length - 1], 10);
    }
  }

  const baseTargetSec = targetSec ? targetSec.replace(/_(us|in|ca)$/, '') : null;
  const localTargetSec = baseTargetSec ? editionSectionKey(baseTargetSec, edition) : targetSec;
  const isSameEditionTarget = !targetSec || targetSec === localTargetSec || (edition === 'ca' && targetSec === baseTargetSec);

  if (baseTargetSec && SECTION_ORDER.includes(baseTargetSec) && Number.isFinite(targetRank) && targetRank > 0) {
    if (isSameEditionTarget) {
      wanted[baseTargetSec] = Math.max(wanted[baseTargetSec] || 0, Math.min(targetRank, MAX_PER_SECTION));
    } else if (!wanted[baseTargetSec]) {
      wanted[baseTargetSec] = 1;
    }
  }

  if (isRapid) {
    const rapidWanted = {};
    for (const key of SECTION_ORDER) rapidWanted[key] = 0;

    // Check available clips for voice in 'top'
    const topSecKey = editionSectionKey('top', edition);
    const topClips = (rows || []).filter((r) => (!id || r.voice === id) && (r.section === topSecKey || (edition === 'ca' && r.section === 'top')));
    const topCount = Math.min(5, topClips.length);
    rapidWanted['top'] = topCount;

    // If 'top' has fewer than 5 clips, backfill from subsequent sections in user order
    let remaining = 5 - topCount;
    if (remaining > 0) {
      for (const key of order) {
        if (key === 'top') continue;
        const edSecKey = editionSectionKey(key, edition);
        const avail = (rows || []).filter((r) => (!id || r.voice === id) && (r.section === edSecKey || (edition === 'ca' && r.section === key))).length;
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
    if (baseTargetSec && targetRank && SECTION_ORDER.includes(baseTargetSec)) {
      rapidWanted[baseTargetSec] = Math.max(rapidWanted[baseTargetSec] || 0, isSameEditionTarget ? Math.min(targetRank, MAX_PER_SECTION) : 1);
    }
    wanted = rapidWanted;
  }

  const chosen = clipsFor(rows, wanted, id, order, edition);
  if (!chosen.length && !matchedRow && !targetAudio) return null;

  const sectionOrderIndex = (sec) => {
    const idx = order.indexOf((sec || '').replace(/_(us|in|ca)$/, ''));
    return idx === -1 ? 999 : idx;
  };

  // Resilient deep-link check:
  // 1. If matchedRow was found in rows but was not in chosen (e.g. cross-region share or disabled section), insert it
  if (matchedRow && !chosen.some((r) => r === matchedRow || storyKey(r) === storyKey(matchedRow) || (r.section === matchedRow.section && r.rank === matchedRow.rank))) {
    const mappedRow = isSameEditionTarget
      ? matchedRow
      : {
          ...matchedRow,
          section: localTargetSec || matchedRow.section,
          rank: 0,
          isSharedBonus: true,
          syntheticId: storyKey(matchedRow),
        };
    chosen.push(mappedRow);
    chosen.sort((a, b) => {
      const secA = sectionOrderIndex(a.section);
      const secB = sectionOrderIndex(b.section);
      if (secA !== secB) return secA - secB;
      return (a.rank || 0) - (b.rank || 0);
    });
  } else if (normalizedTargetStory && !matchedRow) {
    const hasTarget = chosen.some((r) => `${r.section}-${r.rank}` === normalizedTargetStory || r.id === normalizedTargetStory || storyKey(r) === normalizedTargetStory);
    if (!hasTarget) {
      const match = (rows || []).find((r) =>
        (!id || r.voice === id) && (`${r.section}-${r.rank}` === normalizedTargetStory || r.id === normalizedTargetStory || storyKey(r) === normalizedTargetStory)
      ) || (rows || []).find((r) => `${r.section}-${r.rank}` === normalizedTargetStory || r.id === normalizedTargetStory || storyKey(r) === normalizedTargetStory);
      if (match) {
        chosen.push(match);
        chosen.sort((a, b) => {
          const secA = sectionOrderIndex(a.section);
          const secB = sectionOrderIndex(b.section);
          if (secA !== secB) return secA - secB;
          return (a.rank || 0) - (b.rank || 0);
        });
      }
    }
  }

  // 2. If the story was voiced in an earlier batch (e.g. morning) and replaced in the evening batch,
  // the audio file remains permanent in Supabase Storage. Inject it as a shared story!
  const hasTargetInChosen = chosen.some((r) =>
    (effectiveHash && (storyKey(r) === effectiveHash || r.key === effectiveHash)) ||
    (targetTitle && titlesMatch(r.title, targetTitle)) ||
    (targetAudio && normAudio(r.audio_path) === normAudio(targetAudio))
  );

  if (targetAudio && !hasTargetInChosen) {
    const sec = (baseTargetSec && SECTION_ORDER.includes(baseTargetSec)) ? (localTargetSec || targetSec) : editionSectionKey('top', edition);
    const cleanHash = effectiveHash || targetAudio.replace(/[^a-zA-Z0-9]/g, '').slice(-8);
    const archivedId = cleanHash || normalizedTargetStory || `shared-${sec}-${cleanHash}`;
    const existingMeta = (rows || []).find((r) =>
      (cleanHash && storyKey(r) === cleanHash) ||
      (targetTitle && titlesMatch(r.title, targetTitle)) ||
      (targetAudio && normAudio(r.audio_path) === normAudio(targetAudio))
    );
    const synImage = existingMeta?.image || targetImage || null;
    const synScript = existingMeta?.script || targetScript || null;
    const finalAudioPath = existingMeta?.audio_path || normAudio(targetAudio);
    const syntheticRow = {
      section: sec,
      rank: 0,
      title: targetTitle || existingMeta?.title || 'Shared Story',
      summary: targetTitle || existingMeta?.summary || 'Shared Story',
      source: targetSource || existingMeta?.source || 'The news',
      url: existingMeta?.url || null,
      image: synImage,
      script: synScript,
      duration: targetDur || existingMeta?.duration || 20,
      audio_path: finalAudioPath,
      isSharedBonus: true,
      syntheticId: archivedId,
    };
    chosen.unshift(syntheticRow);
    chosen.sort((a, b) => {
      const secA = sectionOrderIndex(a.section);
      const secB = sectionOrderIndex(b.section);
      if (secA !== secB) return secA - secB;
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
    if (isPodcast) return;
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
    if (pod.regionalTease) {
      sayBanter(pod.regionalTease, targetSections[0]);
    }
  } else {
    sayNote(greetingKey(hour));
  }

  let storyPlayed = false;
  let currentSection = null;
  const podHosts = isPodcast ? (pod.hosts || '').split('+').filter(Boolean) : [];
  let storyIndex = 0;
  for (const row of chosen) {
    // In rapid mode, skip section intros to deliver a swift, continuous headline flow
    if (!isRapid && row.section !== currentSection) {
      if (storyPlayed) breath();
      const baseSec = (row.section || '').replace(/_(us|in|ca)$/, '');
      if (isPodcast) {
        // If this is the first section and regionalTease already played at the start,
        // jump directly into the top stories without repeating an intro.
        const isFirstSec = currentSection === null;
        if (!isFirstSec || !pod.regionalTease) {
          const intro = pod.bridges.get(row.section) || pod.bridges.get(baseSec);
          if (intro) sayBanter(intro, row.section);
        }
      } else {
        sayNote(byKey.has(`intro_${row.section}`) ? `intro_${row.section}` : `intro_${baseSec}`);
      }
      currentSection = row.section;
    } else if (storyPlayed) {
      breath();
    }
    // In podcast mode, prefer the two-host conversation clip (`matthew_reference+kelly_reference`),
    // or alternate between solo host recordings on legacy archive packs.
    let storyRow = row;
    if (isPodcast && podHosts.length > 1) {
      const duoId = podHosts.join('+');
      const duoMatch = (rows || []).find((r) => r.section === row.section && r.rank === row.rank && r.voice === duoId)
        || (rows || []).find((r) => storyKey(r) === storyKey(row) && r.voice === duoId);
      if (duoMatch) {
        storyRow = duoMatch;
      } else if (!row.isSharedBonus) {
        const targetVoice = podHosts[storyIndex % podHosts.length];
        const match = (rows || []).find((r) => r.section === row.section && r.rank === row.rank && r.voice === targetVoice);
        if (match) storyRow = match;
      }
      storyIndex++;
    }
    const duration = Number(storyRow.duration) || 0;
    const start = round(cursor);
    const end = round(cursor + duration);
    const key = storyKey(storyRow);
    const id = storyRow.syntheticId || `${storyRow.section}-${storyRow.rank}`;
    stories.push({
      id, key, section: storyRow.section, source: storyRow.source || '',
      headline: storyRow.title,
      summary: storyRow.summary || stripHeadlineAndFiller(storyRow.title, storyRow.script || ''),
      url: storyRow.url || null,
      image: storyRow.image || targetImage || null, start, end, rapid: isRapid,
      audio_path: storyRow.audio_path,
      isSharedBonus: Boolean(storyRow.isSharedBonus),
      date: storyRow.date || date,
      script: storyRow.script || targetScript || storyRow.summary || '',
    });
    chapters.push({ id, key, kind: 'story', title: storyRow.title, start, end, section: storyRow.section });
    clips.push({
      id, key, url: clipUrl(storyRow.audio_path), duration, section: storyRow.section, rank: storyRow.rank,
      title: storyRow.title, start, end,
    });
    storyPlayed = true;
    counts.set(storyRow.section, (counts.get(storyRow.section) || 0) + 1);
    cursor += duration;
  }

  // The sign-off, after a breath, so the brief does not stop dead on the last story.
  if (storyPlayed) breath();
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
    edition: edition || 'ca',
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
