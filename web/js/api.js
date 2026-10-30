// Data access: Supabase (auth, tables) with row-level security keeping each user to their own rows.
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from '../config.js';

// Pre-bundled client served from same-origin vendor bundle (0 cascading CDN network hops)
const createClient = (typeof window !== 'undefined' && window.supabase?.createClient)
  || (typeof globalThis !== 'undefined' && globalThis.supabase?.createClient);

export const sb = createClient ? createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
}) : null;

/** Briefing sections in reading order — the pack categories (app/topics.py). */
export const SECTIONS = {
  // Canada (default)
  top: { title: 'Top stories', emoji: '📰', icon: 'globe' },
  politics: { title: 'Politics', emoji: '🏛️', icon: 'landmark' },
  entertainment: { title: 'Entertainment', emoji: '🎬', icon: 'film' },
  sports: { title: 'Sports', emoji: '🏅', icon: 'ball' },

  // Shared global sections
  ai: { title: 'AI', emoji: '🤖', icon: 'bot' },
  tech: { title: 'Tech', emoji: '💻', icon: 'chip' },
  science: { title: 'Science', emoji: '🔬', icon: 'flask' },

  // United States
  top_us: { title: 'Top stories', emoji: '📰', icon: 'globe' },
  tech_us: { title: 'Tech', emoji: '💻', icon: 'chip' },
  politics_us: { title: 'Politics', emoji: '🏛️', icon: 'landmark' },
  entertainment_us: { title: 'Entertainment', emoji: '🎬', icon: 'film' },
  sports_us: { title: 'Sports', emoji: '🏈', icon: 'ball' },

  // India
  top_in: { title: 'Top stories', emoji: '📰', icon: 'globe' },
  tech_in: { title: 'Tech', emoji: '💻', icon: 'chip' },
  politics_in: { title: 'Politics', emoji: '🏛️', icon: 'landmark' },
  entertainment_in: { title: 'Entertainment', emoji: '🎬', icon: 'film' },
  sports_in: { title: 'Cricket & Sports', emoji: '🏏', icon: 'ball' },

  // Not part of the narrated pack: the Sources tab's user-pasted links keep their own bucket.
  custom: { title: 'My Sources', emoji: '⭐', icon: 'spark' },
};

export const EDITIONS = {
  ca: {
    code: 'ca',
    name: 'Canada',
    flag: '🇨🇦',
    flagSvg: '<svg class="flag-icon" viewBox="0 0 24 16" width="18" height="12" aria-hidden="true" style="border-radius:2px;overflow:hidden;box-shadow:0 0 1px rgba(0,0,0,0.4);"><rect width="6" height="16" fill="#e01a22"/><rect x="6" width="12" height="16" fill="#ffffff"/><rect x="18" width="6" height="16" fill="#e01a22"/><path d="M12 3.2l.7 2.1 1.7-.8-.5 1.9 2.1.4-1.5 1.4.6 2.1-1.9-1.2-1.2 2.2V9.8l-1.2-2.2-1.9 1.2.6-2.1-1.5-1.4 2.1-.4-.5-1.9 1.7.8z" fill="#e01a22"/></svg>',
    label: 'Canada (CA)',
  },
  us: {
    code: 'us',
    name: 'United States',
    flag: '🇺🇸',
    flagSvg: '<svg class="flag-icon" viewBox="0 0 24 16" width="18" height="12" aria-hidden="true" style="border-radius:2px;overflow:hidden;box-shadow:0 0 1px rgba(0,0,0,0.4);"><rect width="24" height="16" fill="#ffffff"/><rect width="24" height="2.46" y="0" fill="#b22234"/><rect width="24" height="2.46" y="4.92" fill="#b22234"/><rect width="24" height="2.46" y="9.84" fill="#b22234"/><rect width="24" height="2.46" y="14.76" fill="#b22234"/><rect width="10" height="8.6" fill="#3c3b6e"/><circle cx="2.5" cy="2.5" r=".7" fill="#fff"/><circle cx="7.5" cy="2.5" r=".7" fill="#fff"/><circle cx="5" cy="4.3" r=".7" fill="#fff"/><circle cx="2.5" cy="6.1" r=".7" fill="#fff"/><circle cx="7.5" cy="6.1" r=".7" fill="#fff"/></svg>',
    label: 'United States (US)',
  },
  in: {
    code: 'in',
    name: 'India',
    flag: '🇮🇳',
    flagSvg: '<svg class="flag-icon" viewBox="0 0 24 16" width="18" height="12" aria-hidden="true" style="border-radius:2px;overflow:hidden;box-shadow:0 0 1px rgba(0,0,0,0.4);"><rect width="24" height="5.33" fill="#ff9933"/><rect y="5.33" width="24" height="5.34" fill="#ffffff"/><rect y="10.67" width="24" height="5.33" fill="#138808"/><circle cx="12" cy="8" r="2.2" fill="none" stroke="#000080" stroke-width="0.8"/><circle cx="12" cy="8" r="0.6" fill="#000080"/></svg>',
    label: 'India (IN)',
  },
};

export function defaultEdition() {
  try {
    // 1. Language & locale check (e.g. 'en-CA', 'fr-CA', 'en-IN', 'hi-IN', 'en-US')
    const nav = typeof navigator !== 'undefined' ? navigator : null;
    const langs = (nav?.languages && nav.languages.length) ? nav.languages : [nav?.language || ''];
    for (const lang of langs) {
      if (!lang) continue;
      const lower = lang.toLowerCase();
      if (lower === 'ca' || lower.endsWith('-ca') || lower.endsWith('_ca')) return 'ca';
      if (lower === 'in' || lower.endsWith('-in') || lower.endsWith('_in')) return 'in';
      if (lower === 'us' || lower.endsWith('-us') || lower.endsWith('_us')) return 'us';
      if (/^(hi|ta|te|mr|bn|gu|kn|ml|pa)([-_]|$)/i.test(lower)) return 'in';
    }

    // 2. Timezone check
    const tz = (typeof Intl !== 'undefined' && Intl.DateTimeFormat)
      ? (Intl.DateTimeFormat().resolvedOptions().timeZone || '')
      : '';
    if (tz.includes('Calcutta') || tz.includes('Kolkata') || tz.includes('India')) return 'in';

    // Canadian timezones
    const canadaTz = [
      'Toronto', 'Vancouver', 'Montreal', 'Edmonton', 'Winnipeg', 'Halifax',
      'St_Johns', 'Regina', 'Yellowknife', 'Iqaluit', 'Whitehorse', 'Moncton',
      'Glace_Bay', 'Goose_Bay', 'Rankin_Inlet', 'Resolute', 'Swift_Current',
      'Dawson', 'Fort_Nelson', 'Cambridge_Bay', 'Inuvik', 'Pangnirtung'
    ];
    if (canadaTz.some((c) => tz.includes(c))) return 'ca';

    // US timezones
    const usTz = [
      'New_York', 'Chicago', 'Los_Angeles', 'Denver', 'Phoenix', 'Detroit',
      'Boise', 'Anchorage', 'Adak', 'Honolulu', 'Juneau', 'Metlakatla',
      'Nome', 'Sitka', 'Yakutat', 'Menominee', 'Indiana', 'Kentucky', 'North_Dakota'
    ];
    if (usTz.some((u) => tz.includes(u))) return 'us';
  } catch {}
  // Default for users outside CA, US, and IN (or unknown): default to Canada or US (default: 'ca')
  return 'ca';
}

/**
 * Detects visitor country from IP geolocation (via edge headers at /api/geo, with fallback).
 * Returns 'ca', 'us', or 'in'. Users outside these countries default to 'ca' or 'us'.
 */
export async function detectEditionFromIp() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2500);
    let res = await fetch('/api/geo', { signal: controller.signal }).catch(() => null);
    let data = res && res.ok ? await res.json().catch(() => null) : null;
    clearTimeout(timer);

    let country = data?.country?.toUpperCase?.();
    if (!country) {
      const c2 = new AbortController();
      const t2 = setTimeout(() => c2.abort(), 2000);
      res = await fetch('https://api.country.is/', { signal: c2.signal }).catch(() => null);
      data = res && res.ok ? await res.json().catch(() => null) : null;
      clearTimeout(t2);
      country = data?.country?.toUpperCase?.();
    }

    if (country === 'IN') return 'in';
    if (country === 'US') return 'us';
    if (country === 'CA') return 'ca';
    // Outside these 3 countries: default to US or Canada
    return 'ca';
  } catch {
    return 'ca';
  }
}

export const sectionLabel = (key) => { const s = SECTIONS[key] || SECTIONS.top; return `${s.emoji} ${s.title}`; };

export const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(`mb-${key}`); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`mb-${key}`, JSON.stringify(value)); } catch { /* storage unavailable */ }
  },
};

/**
 * The narrators the pack records (app/storypack.py). C-3PO serves as the permanent flagship anchor,
 * accompanied by modular neural narrators that can rotate or be customized.
 */
export const BUILTIN_VOICES = [
  { id: 'c3po_reference', name: 'C-3PO', gender: 'male', desc: 'Polite protocol droid', style: 'Polite & Precise', icon: 'bot', builtin: true },
  { id: 'matthew_reference', name: 'Matthew', gender: 'male', desc: 'Calm American newsreader', style: 'Conversational', icon: 'mic', builtin: true },
  { id: 'kelly_reference', name: 'Kelly', gender: 'female', desc: 'Engaging American newsreader', style: 'Clear & Engaging', icon: 'mic', builtin: true },
];

/** The narrator a new visitor hears first: C-3PO is the flagship default narrator. */
export const DEFAULT_VOICE_ID = 'c3po_reference';

export function getCustomVoices() {
  return store.get('custom_voices', []);
}

export function getAllVoices() {
  const custom = getCustomVoices();
  const map = new Map(BUILTIN_VOICES.map((v) => [v.id, v]));
  for (const c of custom) {
    map.set(c.id, { ...c, builtin: false });
  }
  return Array.from(map.values());
}

export const VOICES = getAllVoices();

export function refreshVoices() {
  VOICES.length = 0;
  VOICES.push(...getAllVoices());
  return VOICES;
}

export function saveCustomVoice(voice) {
  const custom = getCustomVoices().filter((v) => v.id !== voice.id);
  custom.push({ ...voice, builtin: false, updated_at: new Date().toISOString() });
  store.set('custom_voices', custom);
  refreshVoices();
  return VOICES;
}

export function deleteCustomVoice(id) {
  const custom = getCustomVoices().filter((v) => v.id !== id);
  store.set('custom_voices', custom);
  refreshVoices();
  return VOICES;
}

/**
 * The voice a listener picked. Matches known narrators or dynamically formats any modular
 * narrator ID so voice rotations render seamlessly without code changes, falling back to C-3PO.
 */
export const voiceFor = (id) => {
  if (!id) return VOICES[0] || BUILTIN_VOICES[0];
  if (typeof id === 'string' && id.includes('+')) {
    const parts = id.split('+').filter(Boolean).map((h) => voiceFor(h).name);
    return {
      id,
      name: parts.join(' & '),
      gender: 'duo',
      desc: 'Podcast co-hosts',
      style: 'Two Hosts',
      icon: 'mic',
      builtin: true,
    };
  }
  const found = VOICES.find((v) => v.id === id);
  if (found) return found;
  const cleanName = id
    .replace(/_reference$/i, '')
    .replace(/_american$/i, '')
    .replace(/_male$/i, '')
    .replace(/_female$/i, '')
    .replace(/_/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    id,
    name: cleanName || id,
    gender: 'neutral',
    desc: 'Neural narrator',
    style: 'Broadcast',
    icon: 'mic',
    builtin: false,
  };
};
export const voiceName = (id) => voiceFor(id).name;

/**
 * Who gets the admin tab. This only decides what the page shows: every admin action is
 * checked again by row-level security and by the worker, so a forged flag gets nowhere.
 */
export const ADMIN_EMAILS = ['vatsakrish@gmail.com'];
export const isAdmin = (profile) =>
  !!profile && (profile.is_admin === true || ADMIN_EMAILS.includes((profile.email || '').toLowerCase()));

export const DEFAULT_SETTINGS = {
  name: '',
  voice: DEFAULT_VOICE_ID,
  speed: 1.0,
  daily: true,
  // Every section starts on, at five stories (the full daily pack), and listeners can dial it down.
  stories: { top: 5, ai: 5, tech: 5, politics: 5, entertainment: 5, science: 5, sports: 5 },
  color_photos: true,
  disabled_sources: [],
};

export function recordError(err, context = '') {
  const rawMsg = typeof err === 'string' ? err : err?.message || String(err || 'Unknown error');
  const entry = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    timestamp: new Date().toISOString(),
    context: context || (typeof window !== 'undefined' ? window.location.pathname : 'app'),
    message: rawMsg,
    stack: err?.stack || null,
  };
  try {
    const logs = store.get('diagnostics-log', []);
    logs.unshift(entry);
    if (logs.length > 50) logs.pop();
    store.set('diagnostics-log', logs);
  } catch {}
  return entry;
}

const FRIENDLY = [
  [/row-level security.*sources/i, 'You can have up to 25 links. Remove one to add another.'],
  [/duplicate key.*sources/i, "You've already added that link."],
  [/check constraint.*url/i, "That doesn't look like a web link (it should start with https://)."],
  [/row-level security.*build_requests/i, 'Only admins can trigger on-demand rebuilds.'],
  [/Failed to fetch|NetworkError|Load failed|timeout|ERR_CONNECTION/i, "Couldn't connect right now. Showing saved content."],
  [/jwt expired|invalid claim|invalid token|refresh_token_not_found/i, 'Your sign-in session expired. Please sign in again.'],
  [/column .* does not exist|relation .* does not exist|violates check constraint/i, 'System synchronization in progress. Please retry.'],
];

export function sanitizeError(err, fallback = "Couldn't reach the service right now. Please try again.") {
  if (!err) return fallback;
  const raw = typeof err === 'string' ? err : err.message || String(err);
  recordError(err, 'sanitized');
  const hit = FRIENDLY.find(([re]) => re.test(raw));
  if (hit) return hit[1];
  if (raw.length < 80 && !raw.includes('Error:') && !raw.includes('violates') && !raw.includes('HTTP ') && !raw.includes('Postgres') && !raw.includes('column') && !raw.includes('relation') && !raw.includes('syntax')) {
    return raw;
  }
  return fallback;
}

function check({ data, error }) {
  if (error) {
    const raw = error.message || String(error);
    recordError(error, 'supabase');
    const hit = FRIENDLY.find(([re]) => re.test(raw));
    throw new Error(hit ? hit[1] : (raw.includes('violates') || raw.includes('does not exist') ? 'System synchronization in progress. Please retry.' : raw));
  }
  return data;
}

let me = null;
async function userId() {
  if (me) return me.id;
  const { data } = await sb.auth.getSession();
  if (!data?.session?.user) throw new Error('Please sign in again.');
  return data.session.user.id;
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

let cachedPublicPack = null;
let cachedPublicPackAt = 0;

export async function publicPack(date = null) {
  const now = Date.now();
  if (cachedPublicPack && now - cachedPublicPackAt < 60000) {
    const cachedDate = cachedPublicPack.date || cachedPublicPack.briefing?.date || '';
    if (!date || !cachedDate || cachedDate === date) {
      return cachedPublicPack;
    }
  }
  const urls = [];
  if (date) {
    urls.push(`${SUPABASE_URL}/storage/v1/object/public/briefings/showcase/pack-${date}.json?t=${Math.floor(now / 60000)}`);
  }
  urls.push(`${SUPABASE_URL}/storage/v1/object/public/briefings/showcase/pack.json?t=${Math.floor(now / 60000)}`);
  urls.push(`${SUPABASE_URL}/storage/v1/object/public/briefings/showcase/sample.json?t=${Math.floor(now / 60000)}`);

  for (const url of urls) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        const obj = await res.json();
        if (obj && (obj.story_audio || obj.rows || obj.briefing)) {
          cachedPublicPack = obj;
          cachedPublicPackAt = now;
          return obj;
        }
      }
    } catch {
      // Continue next URL
    }
  }
  return null;
}

export const api = {
  // ------------------------------------------------------------------ auth
  session: async () => (await sb.auth.getSession()).data?.session || null,
  // Signs in, or creates the account on first use. The email links back here (plus a code if the template has one).
  sendCode: async (email) => {
    const isNative = Boolean(typeof window !== 'undefined' && (window.HarkNative?.isNativeShell?.() || window.Capacitor?.isNativePlatform?.()));
    const redirectUrl = (typeof window !== 'undefined' && window.HarkNative?.getAuthRedirectUrl?.())
      || (isNative ? 'me.vattitude.morningbrief://auth' : location.origin);
    return check(await sb.auth.signInWithOtp({
      email, options: { shouldCreateUser: true, emailRedirectTo: redirectUrl },
    }));
  },
  // Redirects to Google, then back here with a session in the URL (detectSessionInUrl picks it up).
  signInWithGoogle: async () => {
    const isNative = Boolean(typeof window !== 'undefined' && (window.HarkNative?.isNativeShell?.() || window.Capacitor?.isNativePlatform?.()));
    const redirectUrl = (typeof window !== 'undefined' && window.HarkNative?.getAuthRedirectUrl?.())
      || (isNative ? 'me.vattitude.morningbrief://auth' : location.origin);

    if (isNative && window.HarkNative?.openAuthUrl) {
      const { data, error } = await sb.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: redirectUrl,
          queryParams: { prompt: 'select_account' },
          skipBrowserRedirect: true,
        },
      });
      if (error) throw error;
      if (data?.url) {
        window.HarkNative.openAuthUrl(data.url);
        return data;
      }
    }

    return check(await sb.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: redirectUrl,
        queryParams: { prompt: 'select_account' },
      },
    }));
  },
  verifyCode: async (email, token) => check(await sb.auth.verifyOtp({ email, token, type: 'email' })),
  signOut: async () => {
    me = null;
    return sb.auth.signOut();
  },

  async profile() {
    try {
      const id = await userId();
      me = check(await sb.from('profiles').select('id,email,is_admin,settings,status').eq('id', id).single());
      return me;
    } catch {
      me = null;
      return null;
    }
  },

  // ------------------------------------------------------------- briefings

  async latest() {
    const rows = check(await sb.from('briefings').select('data').order('date', { ascending: false }).limit(1));
    return { briefing: rows[0]?.data || null };
  },
  async briefing(day) {
    const rows = check(await sb.from('briefings').select('data').eq('date', day).limit(1));
    return { briefing: rows[0]?.data || null };
  },
  /** The shared per-day clips every listener is merged from (see app/storypack.py). */
  async storyAudio(day) {
    const base = 'date,section,rank,voice,title,url,source';
    const rest = 'script,duration,audio_path';
    try {
      const res = await sb.from('story_audio')
        .select(`${base},image,${rest}`).eq('date', day);
      const rows = check(res);
      if (rows && rows.length > 0) return rows;
    } catch {
      try {
        const res = await sb.from('story_audio')
          .select(`${base},${rest}`).eq('date', day);
        const rows = check(res);
        if (rows && rows.length > 0) return rows;
      } catch {
        // Fall back to storage CDN
      }
    }
    const pack = await publicPack(day);
    if (!pack) return [];
    const packDate = pack.date || pack.briefing?.date || '';
    if (day && packDate && packDate !== day) return [];
    return pack.story_audio || pack.rows || [];
  },
  async storyDates() {
    try {
      const rows = check(await sb.from('story_audio').select('date').order('date', { ascending: false }).limit(120));
      if (rows && rows.length > 0) return [...new Set(rows.map((r) => r.date))];
    } catch {
      // Fall back
    }
    const latest = await this.latestStoryDate();
    return latest ? [latest] : [];
  },
  /** The day's greeting and section intros (see app/storypack.py). */
  async voiceNotes(day) {
    try {
      const rows = check(await sb.from('voice_notes')
        .select('voice,note_key,text,duration,audio_path').eq('date', day));
      if (rows && rows.length > 0) return rows;
    } catch {
      // Fall back to storage CDN
    }
    const pack = await publicPack(day);
    if (!pack) return [];
    const packDate = pack.date || pack.briefing?.date || '';
    if (day && packDate && packDate !== day) return [];
    return pack.voice_notes || pack.notes || [];
  },
  /** The day's podcast banter pieces (see app/podcast.py). Empty when the mode is off or not built. */
  async podcastClips(day) {
    try {
      const rows = check(await sb.from('podcast_clips')
        .select('hosts,clip_key,text,duration,audio_path').eq('date', day));
      if (rows && rows.length > 0) return rows;
    } catch {
      // Fall back
    }
    const pack = await publicPack(day);
    if (!pack) return [];
    const packDate = pack.date || pack.briefing?.date || '';
    if (day && packDate && packDate !== day) return [];
    return pack.podcast_clips || [];
  },
  /** The most recent date that has a pack — used when today's hasn't been published yet. */
  async latestStoryDate(edition = null) {
    try {
      let query = sb.from('story_audio').select('date').order('date', { ascending: false });
      if (edition === 'in') query = query.like('section', '%_in');
      else if (edition === 'us') query = query.like('section', '%_us');
      else if (edition === 'ca') query = query.eq('section', 'top');
      const rows = check(await query.limit(1));
      if (rows && rows[0]?.date) return rows[0].date;
    } catch {
      // Fall back to storage CDN
    }
    const pack = await publicPack();
    const packDate = pack?.date || pack?.briefing?.date || null;
    return packDate || null;
  },
  async archive() {
    try {
      const rows = check(await sb.from('briefings').select('date').order('date', { ascending: false }));
      return { briefings: rows || [] };
    } catch {
      return { briefings: [] };
    }
  },
  async status() {
    try {
      const rows = check(await sb.from('app_status').select('data').eq('id', 1).limit(1));
      return rows[0]?.data || {};
    } catch {
      return {};
    }
  },

  // ------------------------------------------------------------------ admin
  /** One day of the shared pack: every clip, note, and podcast banter clip, so the admin page can summarise it. */
  async packState(day) {
    const [clips, notes, podcastClips] = await Promise.all([
      check(await sb.from('story_audio').select('section,rank,voice,duration').eq('date', day)) || [],
      check(await sb.from('voice_notes').select('voice,note_key,duration').eq('date', day)) || [],
      sb.from('podcast_clips').select('hosts,clip_key,duration').eq('date', day).then((r) => r.data || []).catch(() => []),
    ]);
    return { clips, notes, podcastClips };
  },
  /** Recent requests. Shows only the admin's own rows until the admin read policy is applied. */
  async packRequests(limit = 15) {
    const rows = check(await sb.from('build_requests')
      .select('id,kind,status,message,created_at,finished_at').order('id', { ascending: false }).limit(limit));
    return rows || [];
  },
  /** What every run of the last few days reported, so a missed push is not a missed morning. */
  async runLog(days = 3, limit = 60) {
    const since = new Date(Date.now() - days * 86400000).toLocaleDateString('en-CA');
    const rows = check(await sb.from('run_log')
      .select('id,run_date,status,title,body,detail,voices,created_at')
      .gte('run_date', since).order('created_at', { ascending: false }).limit(limit));
    return rows || [];
  },
  /** Asks the worker to re-voice the pack. The options mirror `python -m app pack`. */
  async queuePack({ day = null, voices = [], edition = null, notesOnly = false, force = false } = {}) {
    const payload = { day, voices, edition, notes_only: notesOnly, force };
    try {
      const row = check(await sb.from('build_requests').insert({ kind: 'pack', payload }).select('id').single());
      return row.id;
    } catch (err) {
      throw new Error(`${err.message} The database needs the admin section of supabase/schema.sql first.`);
    }
  },

  /** Upload formatted reference WAV to Supabase storage. */
  async uploadVoiceFile(voiceId, wavBlob) {
    const path = `voices/${voiceId}.wav`;
    try {
      const res = await sb.storage.from('briefings').upload(path, wavBlob, {
        upsert: true,
        contentType: 'audio/wav',
      });
      return { ok: !res.error, path, error: res.error?.message };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  },

  // -------------------------------------------------------------- requests
  async request(kind) {
    const row = check(await sb.from('build_requests').insert({ kind }).select('id').single());
    return row.id;
  },
  async waitForRequest(id, { timeoutMs = 20 * 60 * 1000, onTick } = {}) {
    const end = Date.now() + timeoutMs;
    while (Date.now() < end) {
      const row = check(await sb.from('build_requests').select('status,message').eq('id', id).single());
      onTick?.(row);
      if (row.status === 'done' || row.status === 'error') return row;
      await wait(3000);
    }
    return { status: 'error', message: "The server hasn't picked this up. It may be asleep; try again after 7 AM." };
  },
  generate: () => api.request('build'),
  // Deletes the account via RPC, direct RLS cleanup, or background worker.
  async deleteAccount({ timeoutMs = 10 * 1000 } = {}) {
    const uid = await userId();
    if (!uid) return;

    // 1. Try instant Supabase RPC deletion (deletes auth.users and cascades everything)
    try {
      const { error } = await sb.rpc('delete_user_account');
      if (!error) return;
    } catch { /* proceed with direct table cleanup */ }

    // 2. Direct cleanup of user tables via RLS
    await Promise.allSettled([
      sb.from('push_subscriptions').delete().eq('user_id', uid),
      sb.from('sources').delete().eq('user_id', uid),
      sb.from('profiles').delete().eq('id', uid),
    ]);

    // 3. Queue delete_account request in case background worker is listening
    let id;
    try { id = await api.request('delete_account'); } catch { return; }
    if (!id) return;

    const end = Date.now() + timeoutMs;
    while (Date.now() < end) {
      await wait(1500);
      const { data, error } = await sb.from('build_requests').select('status,message').eq('id', id).maybeSingle();
      if (error || !data) return; // Row deleted with account
      if (data.status === 'error') throw new Error(data.message || "Your account couldn't be deleted.");
      if (data.status === 'done') return;
    }
  },

  // --------------------------------------------------------------- sources
  async report({ reason, note, headline, summary, url, source }) {
    return check(await sb.from('content_reports').insert({
      reason, note, headline, summary, url, source, writer: 'web', app: 'web',
    }));
  },
  async sources() {
    let rows = [];
    try {
      rows = check(await sb.from('sources').select('*').order('id'));
    } catch { /* guest or offline */ }
    const profile = await api.profile();
    const guest = store.get('guest-settings', {});
    const disabled = new Set(profile?.settings?.disabled_sources || guest.disabled_sources || []);
    return {
      sources: (rows || []).map((s) => ({ ...s, builtin: s.user_id == null, enabled: s.user_id == null ? !disabled.has(s.id) : s.enabled })),
    };
  },
  async addSource({ url, section, name }) {
    const row = check(await sb.from('sources').insert({ url, section, name: name || url }).select().single());
    return { source: row };
  },
  async updateSource(source, body) {
    if (source.builtin) {
      const profile = await api.profile();
      if (profile) {
        const disabled = new Set(profile.settings?.disabled_sources || []);
        if (body.enabled) disabled.delete(source.id); else disabled.add(source.id);
        return api.saveSettings({ disabled_sources: [...disabled] });
      }
      const guest = store.get('guest-settings', {});
      const disabled = new Set(guest.disabled_sources || []);
      if (body.enabled) disabled.delete(source.id); else disabled.add(source.id);
      return api.saveSettings({ disabled_sources: [...disabled] });
    }
    return check(await sb.from('sources').update(body).eq('id', source.id));
  },
  deleteSource: async (id) => check(await sb.from('sources').delete().eq('id', id)),

  // -------------------------------------------------------------- settings
  async settings() {
    const profile = await api.profile();
    if (profile) {
      const stored = profile.settings || {};
      return { settings: { ...DEFAULT_SETTINGS, ...stored, stories: { ...DEFAULT_SETTINGS.stories, ...(stored.stories || {}) } } };
    }
    const guest = store.get('guest-settings', {});
    return { settings: { ...DEFAULT_SETTINGS, ...guest, stories: { ...DEFAULT_SETTINGS.stories, ...(guest.stories || {}) } } };
  },
  async saveSettings(values) {
    const profile = await api.profile();
    if (profile) {
      const settings = { ...(profile.settings || {}), ...values };
      check(await sb.from('profiles').update({ settings }).eq('id', profile.id));
      me = { ...profile, settings };
      return { settings };
    }
    const guest = store.get('guest-settings', {});
    const settings = {
      ...DEFAULT_SETTINGS,
      ...guest,
      ...values,
      stories: { ...DEFAULT_SETTINGS.stories, ...(guest.stories || {}), ...(values.stories || {}) },
    };
    store.set('guest-settings', settings);
    return { settings };
  },

  // ------------------------------------------------------------------ push
  async pushSubscribe(sub) {
    const row = { endpoint: sub.endpoint, p256dh: sub.keys.p256dh, auth: sub.keys.auth, user_id: await userId() };
    return check(await sb.from('push_subscriptions').upsert(row, { onConflict: 'endpoint', ignoreDuplicates: true }));
  },
  pushUnsubscribe: async (sub) => check(await sb.from('push_subscriptions').delete().eq('endpoint', sub.endpoint)),
  async pushTest() {
    const id = await api.request('push_test');
    return api.waitForRequest(id, { timeoutMs: 3 * 60 * 1000 });
  },

  // ----------------------------------------------------------- diagnostics
  diagnostics: () => store.get('diagnostics-log', []),
  clearDiagnostics: () => { store.set('diagnostics-log', []); },
};

// Tiny DOM helper: h('div', {class: 'x', onclick}, child, 'text')
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'html') el.innerHTML = v; // only ever used with static markup
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const icon = (name, cls = '') => {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  if (cls) svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
};

export const fmtTime = (s) => {
  if (!Number.isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
};

export function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return new Date(iso).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' });
}

// "07:05" → "7:05 AM"
export function clockLabel(hhmm) {
  if (!hhmm) return '';
  const [hr, min] = hhmm.split(':').map(Number);
  return new Date(2000, 0, 1, hr, min).toLocaleTimeString('en-CA', { hour: 'numeric', minute: '2-digit' });
}

let toastTimer;
export function toast(message, { error = false, type = null, ms = 3800 } = {}) {
  const el = document.getElementById('toast');
  if (!el) return;
  const isErr = !!error || type === 'error';

  let cleanMsg = message;
  if (isErr && typeof message === 'string') {
    cleanMsg = sanitizeError(message, "Unable to complete request. Please try again.");
  }

  el.className = 'toast';
  if (isErr) el.classList.add('toast-error');
  else if (type === 'success') el.classList.add('toast-success');
  else el.classList.add('toast-info');

  el.replaceChildren();
  const dot = document.createElement('span');
  dot.className = 'toast-dot';
  dot.setAttribute('aria-hidden', 'true');
  const text = document.createElement('span');
  text.className = 'toast-text';
  text.textContent = cleanMsg;
  el.append(dot, text);

  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}
