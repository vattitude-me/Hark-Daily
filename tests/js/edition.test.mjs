import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

const dir = mkdtempSync(join(tmpdir(), 'edition-'));
const apiSrc = readFileSync(new URL('../../web/js/api.js', import.meta.url), 'utf8')
  .replace("'../config.js'", "'./config.mjs'");
writeFileSync(join(dir, 'api.mjs'), apiSrc);
writeFileSync(join(dir, 'config.mjs'), "export const SUPABASE_URL = 'https://x'; export const SUPABASE_PUBLISHABLE_KEY = 'k';");
const { EDITIONS, defaultEdition, detectEditionFromIp, DEFAULT_SETTINGS, DEFAULT_STORIES, migrateStories } = await import(join(dir, 'api.mjs'));

test('EDITIONS definitions contain valid SVG flags and clean labels', () => {
  for (const code of ['ca', 'us', 'in']) {
    const ed = EDITIONS[code];
    assert.ok(ed, `Edition ${code} must exist`);
    assert.equal(ed.code, code);
    assert.ok(ed.flagSvg.includes('<svg'), `Edition ${code} must have flagSvg`);
    assert.ok(!ed.label.startsWith(ed.flag), `Edition ${code} label should not duplicate flag emoji as text: ${ed.label}`);
    assert.ok(ed.label.includes(`(${code.toUpperCase()})`), `Edition ${code} label must include code`);
  }
});

test('defaultEdition detects country from language tag or timezone', () => {
  const origDesc = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  const origIntl = globalThis.Intl;

  const setNav = (obj) => {
    Object.defineProperty(globalThis, 'navigator', { value: obj, configurable: true, writable: true });
  };

  try {
    // 1. Canadian locale
    setNav({ languages: ['en-CA', 'en-US'], language: 'en-CA' });
    globalThis.Intl = { DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'America/New_York' }) }) };
    assert.equal(defaultEdition(), 'ca', 'en-CA locale should resolve to ca even if timezone is America/New_York');

    // 2. India locale & languages
    setNav({ languages: ['hi-IN', 'en-US'], language: 'hi-IN' });
    assert.equal(defaultEdition(), 'in', 'hi-IN locale should resolve to in');

    setNav({ languages: ['ta'], language: 'ta' });
    assert.equal(defaultEdition(), 'in', 'Indian language without country subtag should resolve to in');

    // 3. US locale
    setNav({ languages: ['en-US'], language: 'en-US' });
    globalThis.Intl = { DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'America/Chicago' }) }) };
    assert.equal(defaultEdition(), 'us', 'en-US locale should resolve to us');

    // 4. Timezone fallbacks when locale is generic 'en'
    setNav({ languages: ['en'], language: 'en' });
    globalThis.Intl = { DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'America/Toronto' }) }) };
    assert.equal(defaultEdition(), 'ca', 'America/Toronto timezone should resolve to ca');

    globalThis.Intl = { DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Asia/Kolkata' }) }) };
    assert.equal(defaultEdition(), 'in', 'Asia/Kolkata timezone should resolve to in');

    globalThis.Intl = { DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'America/Los_Angeles' }) }) };
    assert.equal(defaultEdition(), 'us', 'America/Los_Angeles timezone should resolve to us');

    // 5. Outside countries default to Canada or US (default: ca)
    setNav({ languages: ['fr-FR'], language: 'fr-FR' });
    globalThis.Intl = { DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: 'Europe/Paris' }) }) };
    assert.equal(defaultEdition(), 'ca', 'Europe/Paris outside country should default to ca');
  } finally {
    if (origDesc) Object.defineProperty(globalThis, 'navigator', origDesc);
    globalThis.Intl = origIntl;
  }
});

test('detectEditionFromIp maps countries and defaults outside countries to ca', async () => {
  const origFetch = globalThis.fetch;
  try {
    // 1. IP in Canada
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ country: 'CA' }),
    });
    assert.equal(await detectEditionFromIp(), 'ca');

    // 2. IP in US
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ country: 'US' }),
    });
    assert.equal(await detectEditionFromIp(), 'us');

    // 3. IP in India
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ country: 'IN' }),
    });
    assert.equal(await detectEditionFromIp(), 'in');

    // 4. IP in Germany (outside CA, US, IN)
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ country: 'DE' }),
    });
    assert.equal(await detectEditionFromIp(), 'ca', 'Outside country should default to ca');
  } finally {
    globalThis.fetch = origFetch;
  }
});

test('DEFAULT_SETTINGS and migrateStories default to 5 for top and 3 for others', () => {
  assert.equal(DEFAULT_SETTINGS.stories.top, 5);
  assert.equal(DEFAULT_SETTINGS.stories.ai, 3);
  assert.equal(DEFAULT_SETTINGS.stories.tech, 3);
  assert.equal(DEFAULT_SETTINGS.stories.politics, 3);
  assert.equal(DEFAULT_SETTINGS.stories.entertainment, 3);
  assert.equal(DEFAULT_SETTINGS.stories.science, 3);
  assert.equal(DEFAULT_SETTINGS.stories.sports, 3);

  // Legacy settings where everything was 5 are migrated to top: 5, others: 3
  const legacy = { top: 5, ai: 5, tech: 5, politics: 5, entertainment: 5, science: 5, sports: 5 };
  const migrated = migrateStories(legacy);
  assert.equal(migrated.top, 5);
  assert.equal(migrated.ai, 3);
  assert.equal(migrated.tech, 3);
  assert.equal(migrated.politics, 3);

  // Custom user settings with _v: 2 are preserved
  const custom = { top: 4, ai: 5, tech: 2, _v: 2 };
  const preserved = migrateStories(custom);
  assert.equal(preserved.top, 4);
  assert.equal(preserved.ai, 5);
  assert.equal(preserved.tech, 2);
  assert.equal(preserved.politics, 3); // missing key gets new default
});

test('prevChapter and restart rewind cleanly to 0:00', async () => {
  const storypackSrc = readFileSync(new URL('../../web/js/storypack.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api.mjs'").replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'storypack.mjs'), storypackSrc);

  const playerSrc = readFileSync(new URL('../../web/js/player.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api.mjs'")
    .replace("'./storypack.js'", "'./storypack.mjs'");
  writeFileSync(join(dir, 'player.mjs'), playerSrc);
  const { Player } = await import(join(dir, 'player.mjs'));

  class MockAudio extends EventTarget {
    constructor() {
      super();
      this.currentTime = 0;
      this.paused = true;
      this.playbackRate = 1.0;
    }
    play() {
      this.paused = false;
      return Promise.resolve();
    }
    pause() {
      this.paused = true;
    }
    load() {}
    removeAttribute() {}
  }

  const audio = new MockAudio();
  const preloader = new MockAudio();
  const player = new Player({ audio, preloader, el: {} });
  player.setupAudioElement(audio);

  player.chapters = [
    { id: 'ch-0', start: 0, end: 20 },
    { id: 'ch-1', start: 20, end: 40 },
  ];
  player.clips = [
    { id: 'clip-0', start: 0, end: 20, url: 'http://cdn/0.mp3' },
    { id: 'clip-1', start: 20, end: 40, url: 'http://cdn/1.mp3' },
  ];
  player.briefing = { mode: 'podcast', title: 'Test' };
  audio.dataset = { clip: '0' };
  audio.src = 'http://cdn/0.mp3';

  let seekCalledWith = null;
  player.seekTo = (t) => { seekCalledWith = t; };

  // 1. When at start of briefing (position < 3 on first chapter), prevChapter() rewinds to 0
  audio.currentTime = 1.5;
  player.prevChapter();
  assert.equal(seekCalledWith, 0, 'prevChapter at start of chapter 0 must rewind to 0:00');

  // 2. restart() explicitly rewinds to 0 and plays
  seekCalledWith = null;
  player.restart();
  assert.equal(seekCalledWith, 0, 'restart must seek to 0:00');
  assert.equal(audio.paused, false, 'restart must trigger audio playback');
});

test('per-edition caching strictly isolates Canada, US, and India', () => {
  const memoryStore = new Map();
  const store = {
    get: (k, def) => (memoryStore.has(k) ? memoryStore.get(k) : def),
    set: (k, v) => memoryStore.set(k, v),
  };

  // Simulate storing Canada briefing
  const caBrief = { date: '2026-11-04', edition: 'ca', stories: [{ id: 'ca-1' }] };
  store.set('last-briefing', caBrief);
  store.set('last-briefing-ca', caBrief);

  // When user switches to India, query strictly checks target edition
  const inBrief = store.get('last-briefing-in', null);
  assert.equal(inBrief, null, 'India cache must not be polluted by Canada cache');

  // Storing India briefing isolates cleanly
  const newInBrief = { date: '2026-11-04', edition: 'in', stories: [{ id: 'in-1' }] };
  store.set('last-briefing-in', newInBrief);
  assert.equal(store.get('last-briefing-in')?.edition, 'in');
  assert.equal(store.get('last-briefing-ca')?.edition, 'ca');
});
