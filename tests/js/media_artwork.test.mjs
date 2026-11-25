import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

const dir = mkdtempSync(join(tmpdir(), 'media-artwork-'));

writeFileSync(join(dir, 'network.js'), readFileSync(new URL('../../web/js/network.js', import.meta.url)));
writeFileSync(
  join(dir, 'storypack.mjs'),
  readFileSync(new URL('../../web/js/storypack.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api.mjs'")
    .replace("'../config.js'", "'./config.mjs'"),
);
writeFileSync(
  join(dir, 'api.mjs'),
  `export const SECTIONS = {
    top: { title: 'Top stories' },
    tech: { title: 'Tech' },
  };
  export const voiceName = (v) => v;
  export const fmtTime = (s) => String(Math.floor(s || 0));
  export const h = () => ({ addEventListener: () => {}, classList: { toggle: () => {} } });
  export const store = { get: (k, def) => (def !== undefined ? def : null), set: () => {} };
  export const VOICES = {};
  export const voiceFor = () => ({});
  export const DEFAULT_VOICE_ID = 'matthew_reference+kelly_reference';
  export const EDITIONS = {};
  export const defaultEdition = () => 'ca';
  export const detectEditionFromIp = () => 'ca';
  export const api = {};
  export const icon = () => ({});
  export const isAdmin = () => false;
  export const recordError = () => {};
  export const sb = null;
  export const timeAgo = () => '';
  export const toast = () => {};`,
);
writeFileSync(
  join(dir, 'config.mjs'),
  "export const SUPABASE_URL = 'https://x'; export const SUPABASE_PUBLISHABLE_KEY = 'k'; export const FEATURES = { podcast: true, rapid: true };",
);
writeFileSync(
  join(dir, 'player.mjs'),
  readFileSync(new URL('../../web/js/player.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api.mjs'")
    .replace("'./storypack.js'", "'./storypack.mjs'"),
);

const { Player, toAbsoluteArtworkUrl } = await import(join(dir, 'player.mjs'));

function createMockElement(id) {
  const listeners = new Map();
  return {
    id,
    textContent: '',
    src: '',
    href: '',
    style: {},
    dataset: {},
    classList: { toggle: () => {}, add: () => {}, remove: () => {}, contains: () => false },
    setAttribute: () => {},
    removeAttribute: () => {},
    querySelectorAll: () => [],
    querySelector: () => null,
    replaceChildren: () => {},
    insertBefore: () => {},
    addEventListener: (type, fn) => {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    dispatchEvent: (ev) => {
      for (const fn of listeners.get(ev.type) || []) fn(ev);
      return true;
    },
  };
}

function createFakeAudio() {
  const listeners = new Map();
  return {
    paused: true,
    ended: false,
    currentTime: 0,
    duration: 40,
    playbackRate: 1,
    volume: 1,
    muted: false,
    readyState: 4,
    dataset: {},
    src: '',
    load: () => {},
    pause: function () { this.paused = true; },
    play: async function () { this.paused = false; },
    removeAttribute: function (attr) { if (attr === 'src') this.src = ''; },
    addEventListener: (type, fn) => {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
  };
}

function setupEnv(t, harkNative) {
  const prevWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const prevDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  const prevNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  const prevMediaMetadata = Object.getOwnPropertyDescriptor(globalThis, 'MediaMetadata');

  const elements = new Map();
  const doc = {
    getElementById: (id) => {
      if (!elements.has(id)) elements.set(id, createMockElement(id));
      return elements.get(id);
    },
    querySelectorAll: () => [],
    querySelector: () => null,
    createElement: () => createMockElement('created'),
    addEventListener: () => {},
    body: { classList: { toggle: () => {} } },
    visibilityState: 'visible',
  };

  class MockMediaMetadata {
    constructor(init) {
      this.title = init.title;
      this.artist = init.artist;
      this.album = init.album;
      this.artwork = init.artwork;
    }
  }

  const mediaSessionState = {
    metadata: null,
    playbackState: 'none',
    positionState: null,
    setActionHandler: () => {},
    setPositionState: (pos) => { mediaSessionState.positionState = pos; },
  };

  Object.defineProperty(globalThis, 'document', { value: doc, configurable: true, writable: true });
  Object.defineProperty(globalThis, 'MediaMetadata', { value: MockMediaMetadata, configurable: true, writable: true });
  Object.defineProperty(globalThis, 'navigator', {
    value: { mediaSession: mediaSessionState },
    configurable: true,
    writable: true,
  });
  Object.defineProperty(globalThis, 'window', {
    value: {
      location: { origin: 'https://hark.vattitude.ca' },
      HarkNative: harkNative,
      trackEvent: () => {},
    },
    configurable: true,
    writable: true,
  });

  t.after(() => {
    const restore = (key, desc) => {
      if (desc) Object.defineProperty(globalThis, key, desc);
      else delete globalThis[key];
    };
    restore('window', prevWindow);
    restore('document', prevDocument);
    restore('navigator', prevNavigator);
    restore('MediaMetadata', prevMediaMetadata);
  });

  return { doc, elements, mediaSessionState };
}

function sampleBriefing() {
  return {
    date: '2026-11-24',
    title: 'Your briefing · Podcast',
    mode: 'podcast',
    edition: 'ca',
    duration: 60,
    sections: [
      { key: 'top', title: 'Top stories', count: 1 },
      { key: 'tech', title: 'Tech', count: 1 },
    ],
    stories: [
      {
        id: 'top-1',
        section: 'top',
        source: 'CBC News · Canada',
        headline: 'Canada expands clean grid interconnect',
        image: 'https://i.cbc.ca/ais/d00da2e6/full/max/0/default',
        start: 10,
        end: 35,
      },
      {
        id: 'tech-1',
        section: 'tech',
        source: 'BetaKit · Tech',
        headline: 'Cohere opens Montreal compute lab',
        image: 'https://cdn.betakit.com/wp-content/uploads/2025/08/Databricks.jpg',
        start: 35,
        end: 60,
      },
    ],
    chapters: [
      { id: 'pod_open_1', kind: 'note', title: 'Good morning', start: 0, end: 10 },
      { id: 'top-1', kind: 'story', title: 'Canada expands clean grid interconnect', start: 10, end: 35, section: 'top' },
      { id: 'tech-1', kind: 'story', title: 'Cohere opens Montreal compute lab', start: 35, end: 60, section: 'tech' },
    ],
    clips: [
      { id: 'pod_open_1', url: 'https://cdn/open.mp3', duration: 10, start: 0, end: 10, note: true, banter: true },
      { id: 'top-1', url: 'https://cdn/top1.mp3', duration: 25, start: 10, end: 35, section: 'top' },
      { id: 'tech-1', url: 'https://cdn/tech1.mp3', duration: 25, start: 35, end: 60, section: 'tech' },
    ],
  };
}

test('Player syncs active story headline, outlet artist, and news image to MediaSession and HarkNative', (t) => {
  const nativeCalls = [];
  const { mediaSessionState } = setupEnv(t, {
    setKeepScreenOn: () => {},
    updatePlaybackMetadata: (playing, title, artist, artworkUrl) => {
      nativeCalls.push({ fn: 'updatePlaybackMetadata', playing, title, artist, artworkUrl });
    },
    notifyPlaybackState: (playing, title, artist) => {
      nativeCalls.push({ fn: 'notifyPlaybackState', playing, title, artist });
    },
  });

  const audio = createFakeAudio();
  const preloader = createFakeAudio();
  const player = new Player({ audio, preloader });
  const briefing = sampleBriefing();
  player.load(briefing);

  // Move playback onto story 1 (top-1) and mark playing
  player.index = 1;
  audio.currentTime = 5; // position = 15s -> inside top-1
  audio.paused = false;
  player.setPlaying(true);

  assert.equal(mediaSessionState.metadata.title, 'Canada expands clean grid interconnect');
  assert.equal(mediaSessionState.metadata.artist, 'CBC News · Hark Daily');
  assert.equal(mediaSessionState.metadata.album, 'Top stories');
  assert.deepEqual(mediaSessionState.metadata.artwork, [
    { src: 'https://i.cbc.ca/ais/d00da2e6/full/max/0/default', sizes: '512x512' },
    { src: 'https://hark.vattitude.ca/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
  ]);

  assert.equal(nativeCalls.length, 1);
  assert.deepEqual(nativeCalls[0], {
    fn: 'updatePlaybackMetadata',
    playing: true,
    title: 'Canada expands clean grid interconnect',
    artist: 'CBC News \u2022 Hark Daily',
    artworkUrl: 'https://i.cbc.ca/ais/d00da2e6/full/max/0/default',
  });

  // Duplicate play event for same track is deduplicated
  player.setPlaying(true);
  assert.equal(nativeCalls.length, 1);

  // Advance to story 2 (tech-1)
  player.index = 2;
  audio.currentTime = 2; // position = 37s -> inside tech-1
  player.tick();

  assert.equal(mediaSessionState.metadata.title, 'Cohere opens Montreal compute lab');
  assert.equal(mediaSessionState.metadata.artwork[0].src, 'https://cdn.betakit.com/wp-content/uploads/2025/08/Databricks.jpg');
  assert.equal(nativeCalls.length, 2);
  assert.equal(nativeCalls[1].title, 'Cohere opens Montreal compute lab');
  assert.equal(nativeCalls[1].artist, 'BetaKit \u2022 Hark Daily');
  assert.equal(nativeCalls[1].artworkUrl, 'https://cdn.betakit.com/wp-content/uploads/2025/08/Databricks.jpg');
});

test('Player falls back to 3-arg notifyPlaybackState when updatePlaybackMetadata is absent', (t) => {
  const legacyCalls = [];
  setupEnv(t, {
    setKeepScreenOn: () => {},
    notifyPlaybackState: (playing, title, artist) => {
      legacyCalls.push({ playing, title, artist });
    },
  });

  const audio = createFakeAudio();
  const player = new Player({ audio, preloader: createFakeAudio() });
  player.load(sampleBriefing());

  player.index = 1;
  audio.currentTime = 4;
  audio.paused = false;
  player.setPlaying(true);

  assert.equal(legacyCalls.length, 1);
  assert.deepEqual(legacyCalls[0], {
    playing: true,
    title: 'Canada expands clean grid interconnect',
    artist: 'CBC News \u2022 Hark Daily',
  });
});

test('Player falls back to PNG icon and refreshes MediaSession + HarkNative when story image fails', (t) => {
  const nativeCalls = [];
  const { elements, mediaSessionState } = setupEnv(t, {
    setKeepScreenOn: () => {},
    updatePlaybackMetadata: (playing, title, artist, artworkUrl) => {
      nativeCalls.push({ playing, title, artist, artworkUrl });
    },
  });

  const audio = createFakeAudio();
  const player = new Player({ audio, preloader: createFakeAudio() });
  player.load(sampleBriefing());

  player.index = 1;
  audio.currentTime = 5;
  audio.paused = false;
  player.tick();
  player.setPlaying(true);

  const coverImg = elements.get('playerCoverImg');
  assert.ok(coverImg, 'playerCoverImg element should be bound');
  coverImg.dataset.src = 'https://i.cbc.ca/ais/d00da2e6/full/max/0/default';
  coverImg.dispatchEvent({ type: 'error' });

  assert.deepEqual(mediaSessionState.metadata.artwork, [
    { src: 'https://hark.vattitude.ca/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
  ]);
  const lastCall = nativeCalls.at(-1);
  assert.equal(lastCall.artworkUrl, 'https://hark.vattitude.ca/icons/icon-512.png');
  assert.equal(toAbsoluteArtworkUrl('/icons/icon-512.png'), 'https://hark.vattitude.ca/icons/icon-512.png');
});

test.after(() => {
  rmSync(dir, { recursive: true, force: true });
});
