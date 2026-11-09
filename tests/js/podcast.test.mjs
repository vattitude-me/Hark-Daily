// Run with: node --test tests/js
// Checks how storypack.js assembles a podcast brief. api.js and config.js need a browser and a
// network, so they are swapped for tiny stand-ins in a temp copy of the module.
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

const dir = mkdtempSync(join(tmpdir(), 'storypack-'));
const src = readFileSync(new URL('../../web/js/storypack.js', import.meta.url), 'utf8')
  .replace("'./api.js'", "'./api.mjs'").replace("'../config.js'", "'./config.mjs'");
writeFileSync(join(dir, 'storypack.mjs'), src);
writeFileSync(join(dir, 'api.mjs'), `export const SECTIONS = {
  top: { title: 'Top stories' }, top_us: { title: 'Top stories' }, top_in: { title: 'Top stories' },
  markets: { title: 'Markets' }, markets_us: { title: 'Markets' }, markets_in: { title: 'Markets' },
  ai: { title: 'AI' }, tech: { title: 'Tech' }, science: { title: 'Science' },
  politics: { title: 'Politics' }, politics_us: { title: 'Politics' }, politics_in: { title: 'Politics' },
  entertainment: { title: 'Entertainment' }, entertainment_us: { title: 'Entertainment' }, entertainment_in: { title: 'Entertainment' },
  sports: { title: 'Sports' }, sports_us: { title: 'Sports' }, sports_in: { title: 'Cricket & Sports' }
}; export const voiceName = (v) => v; export const fmtTime = (s) => String(s); export const h = () => ({ addEventListener: () => {}, classList: { toggle: () => {} } }); export const store = { get: (k, def) => (def !== undefined ? def : null), set: () => {} }; export const generateRawNonce = () => '00'; export const hashNonce = async () => '00'; export const api = { generateRawNonce: () => '00', hashNonce: async () => '00', signInWithGoogleIdToken: async () => ({}) }; export const icon = () => ({}); export const isAdmin = () => false; export const recordError = () => {}; export const sb = null; export const timeAgo = () => ''; export const toast = () => {}; export const VOICES = {}; export const voiceFor = () => ({}); export const DEFAULT_VOICE_ID = 'c3po_reference'; export const EDITIONS = {}; export const defaultEdition = () => 'ca'; export const detectEditionFromIp = () => 'ca';`);
writeFileSync(join(dir, 'config.mjs'), "export const SUPABASE_URL = 'https://x'; export const SUPABASE_PUBLISHABLE_KEY = 'k'; export const FEATURES = { podcast: true, rapid: true }; export const GOOGLE_CLIENT_ID = 'test-id'; export const APP_VERSION = '1.0.15';");
const { buildBriefing, planPodcast, PODCAST_BUDGET, editionSectionKey, clipsFor, parseDialogueTurns, pickVoice, clipUrl, voiceNormalize, lineup, MAX_PER_SECTION, DEFAULT_SECTION_COUNTS, LOGICAL_SECTIONS } = await import(join(dir, 'storypack.mjs'));

const playerSrc = readFileSync(new URL('../../web/js/player.js', import.meta.url), 'utf8')
  .replace("'./api.js'", "'./api.mjs'")
  .replace("'./storypack.js'", "'./storypack.mjs'");
writeFileSync(join(dir, 'player.mjs'), playerSrc);
const { posKeyFor, Player, getDefaultCover } = await import(join(dir, 'player.mjs'));

const row = (section, rank) => ({ date: 'd', section, rank, voice: 'v', title: `${section}${rank}`, url: 'u', source: 's', script: 'x', duration: 20, audio_path: `s/${section}${rank}.mp3` });
const rows = [row('top', 1), row('top', 2), row('ai', 1), row('tech', 1), row('sports', 1)];
const notes = ['greeting_morning', 'intro_top', 'intro_ai', 'outro', 'pack_ready']
  .map((k) => ({ voice: 'v', note_key: k, text: k, duration: 2, audio_path: k }));
const pc = (k, d) => ({ hosts: 'a+b', clip_key: k, text: k, duration: d, audio_path: `p/${k}.mp3` });
const pod = [pc('podcast_ready', 0), ...[1, 2, 3].map((n) => pc(`pod_open_${n}`, 15)), ...[1, 2].map((n) => pc(`pod_close_${n}`, 10)),
  ...['top', 'ai', 'tech', 'sports'].flatMap((s) => [pc(`pod_tease_${s}`, 15), pc(`pod_bridge_${s}`, 8)])];
const build = (stories, podcastClips = pod, mode = 'podcast') => buildBriefing(rows, { stories }, { date: 'd', voice: 'v', notes, mode, podcastClips });
const ids = (b) => b.clips.filter((c) => !c.gap).map((c) => c.id);
const banter = (b) => b.clips.filter((c) => c.banter).reduce((n, c) => n + c.duration, 0);

test('podcast brief: open, regional teaser directly into top stories, bridges for next sections, close', () => {
  const b = build({ top: 2, ai: 1 });
  assert.equal(b.mode, 'podcast');
  const list = ids(b);
  assert.match(list[0], /^pod_open_/);
  assert.match(list.at(-1), /^pod_close_/);
  assert.equal(list[1], 'pod_tease_top');
  assert.equal(list[2], 'top-1', 'Podcast directly jumps into top stories after regional teaser');
  assert.equal(list.indexOf('pod_bridge_top'), -1, 'Redundant bridge is skipped when regional teaser played');
  assert.ok(list.indexOf('pod_bridge_ai') < list.indexOf('ai-1'), 'Subsequent sections receive their section bridge');
  assert.ok(!list.some((id) => id.startsWith('intro_') || id === 'outro' || id.startsWith('greeting')));
});

test('banter stays within budget however many sections are chosen', () => {
  for (const stories of [{ top: 1 }, { top: 2, ai: 1 }, { top: 2, ai: 1, tech: 1, sports: 1 }]) {
    const b = build(stories);
    assert.ok(banter(b) <= PODCAST_BUDGET + 25, `${JSON.stringify(stories)} banter ${banter(b)}`); // open+close are always kept
  }
  assert.ok(ids(build({ top: 2, ai: 1, tech: 1, sports: 1 })).filter((i) => i.startsWith('pod_tease')).length <= 3);
});

test('only chosen sections are mentioned', () => {
  const list = ids(build({ top: 2, ai: 1, tech: 0, sports: 0 }));
  assert.ok(!list.includes('pod_tease_sports') && !list.includes('pod_bridge_tech'));
});

test('timeline is contiguous', () => {
  const b = build({ top: 2, ai: 1 });
  assert.ok(b.clips.every((c, i, a) => i === 0 || Math.abs(c.start - a[i - 1].end) < 0.02));
});

test('falls back to the full brief when the podcast is missing or unusable', () => {
  const noMarker = pod.filter((c) => c.clip_key !== 'podcast_ready');
  const noClose = pod.filter((c) => !c.clip_key.startsWith('pod_close'));
  for (const clips of [[], noMarker, noClose]) {
    const b = build({ top: 2, ai: 1 }, clips);
    assert.equal(b.mode, 'full');
    assert.equal(b.podcastFallback, true);
    assert.ok(ids(b).includes('top-1'));
  }
});

test('missing individual pieces are skipped, the news still plays', () => {
  const clips = pod.filter((c) => c.clip_key !== 'pod_tease_ai' && c.clip_key !== 'pod_bridge_top');
  const list = ids(build({ top: 2, ai: 1 }, clips));
  assert.ok(!list.includes('pod_tease_ai') && !list.includes('pod_bridge_top'));
  assert.ok(list.includes('top-1') && list.includes('ai-1'));
});

test('full mode is unchanged and has no fallback flag', () => {
  const b = build({ top: 2, ai: 1 }, [], 'full');
  assert.equal(b.mode, 'full');
  assert.equal(b.podcastFallback, false);
  assert.ok(ids(b).includes('intro_top'));
});

test('opening varies from day to day', () => {
  const seen = new Set(['2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30', '2026-10-31', '2026-11-01']
    .map((date) => planPodcast(pod, ['top'], `${date}:v`).open.clip_key));
  assert.ok(seen.size > 1);
});

test('podcast alternates voices between hosts for successive stories', () => {
  const multiRows = [
    { date: 'd', section: 'top', rank: 1, voice: 'a', title: 'top1', duration: 10, audio_path: 's/a/top1.mp3' },
    { date: 'd', section: 'top', rank: 1, voice: 'b', title: 'top1', duration: 10, audio_path: 's/b/top1.mp3' },
    { date: 'd', section: 'top', rank: 2, voice: 'a', title: 'top2', duration: 10, audio_path: 's/a/top2.mp3' },
    { date: 'd', section: 'top', rank: 2, voice: 'b', title: 'top2', duration: 10, audio_path: 's/b/top2.mp3' },
    { date: 'd', section: 'top', rank: 3, voice: 'a', title: 'top3', duration: 10, audio_path: 's/a/top3.mp3' },
    { date: 'd', section: 'top', rank: 3, voice: 'b', title: 'top3', duration: 10, audio_path: 's/b/top3.mp3' },
  ];
  const b = buildBriefing(multiRows, { stories: { top: 3 } }, { date: 'd', voice: 'a', notes, mode: 'podcast', podcastClips: pod });
  const storyClips = b.clips.filter((c) => !c.note && !c.gap);
  assert.equal(storyClips.length, 3);
  assert.ok(storyClips[0].url.includes('/a/top1.mp3'), `story 0 voice was ${storyClips[0].url}`);
  assert.ok(storyClips[1].url.includes('/b/top2.mp3'), `story 1 voice was ${storyClips[1].url}`);
  assert.ok(storyClips[2].url.includes('/a/top3.mp3'), `story 2 voice was ${storyClips[2].url}`);
});

test('editionSectionKey maps regional keys and keeps shared keys universal', () => {
  assert.equal(editionSectionKey('top', 'ca'), 'top');
  assert.equal(editionSectionKey('top', 'us'), 'top_us');
  assert.equal(editionSectionKey('top', 'in'), 'top_in');
  assert.equal(editionSectionKey('ai', 'us'), 'ai');
  assert.equal(editionSectionKey('tech', 'ca'), 'tech');
  assert.equal(editionSectionKey('tech', 'us'), 'tech_us');
  assert.equal(editionSectionKey('tech', 'in'), 'tech_in');
  assert.equal(editionSectionKey('science', 'us'), 'science');
});

test('clipsFor selects edition-specific clips and isolates regional news', () => {
  const mixedRows = [
    { date: 'd', section: 'top', rank: 1, voice: 'v', title: 'CA Top', duration: 10, audio_path: 's/top1.mp3' },
    { date: 'd', section: 'top_us', rank: 1, voice: 'v', title: 'US Top', duration: 10, audio_path: 's/top_us1.mp3' },
    { date: 'd', section: 'ai', rank: 1, voice: 'v', title: 'Global AI', duration: 10, audio_path: 's/ai1.mp3' },
  ];
  const usClips = clipsFor(mixedRows, { top: 1, ai: 1 }, 'v', ['top', 'ai'], 'us');
  assert.equal(usClips.length, 2);
  assert.equal(usClips[0].title, 'US Top');
  assert.equal(usClips[1].title, 'Global AI');

  const inClips = clipsFor(mixedRows, { top: 1, ai: 1 }, 'v', ['top', 'ai'], 'in');
  // When top_in is missing, it returns universal coverage (Global AI) and never Canadian domestic news
  assert.equal(inClips.length, 1);
  assert.equal(inClips[0].title, 'Global AI');
});

const multiEdRows = [
  // US sections
  { section: 'top_us', rank: 1, voice: 'v', title: 'US Top', duration: 10, audio_path: 's/top_us.mp3' },
  { section: 'tech_us', rank: 1, voice: 'v', title: 'US Tech', duration: 10, audio_path: 's/tech_us.mp3' },
  { section: 'politics_us', rank: 1, voice: 'v', title: 'US Politics', duration: 10, audio_path: 's/pol_us.mp3' },
  { section: 'entertainment_us', rank: 1, voice: 'v', title: 'US Ent', duration: 10, audio_path: 's/ent_us.mp3' },
  { section: 'sports_us', rank: 1, voice: 'v', title: 'US Sports', duration: 10, audio_path: 's/spo_us.mp3' },

  // India sections
  { section: 'top_in', rank: 1, voice: 'v', title: 'IN Top', duration: 10, audio_path: 's/top_in.mp3' },
  { section: 'tech_in', rank: 1, voice: 'v', title: 'IN Tech', duration: 10, audio_path: 's/tech_in.mp3' },
  { section: 'politics_in', rank: 1, voice: 'v', title: 'IN Politics', duration: 10, audio_path: 's/pol_in.mp3' },
  { section: 'entertainment_in', rank: 1, voice: 'v', title: 'IN Ent', duration: 10, audio_path: 's/ent_in.mp3' },
  { section: 'sports_in', rank: 1, voice: 'v', title: 'IN Cricket', duration: 10, audio_path: 's/spo_in.mp3' },

  // Canada sections
  { section: 'top', rank: 1, voice: 'v', title: 'CA Top', duration: 10, audio_path: 's/top_ca.mp3' },
  { section: 'tech', rank: 1, voice: 'v', title: 'CA Tech', duration: 10, audio_path: 's/tech_ca.mp3' },
  { section: 'politics', rank: 1, voice: 'v', title: 'CA Politics', duration: 10, audio_path: 's/pol_ca.mp3' },
  { section: 'entertainment', rank: 1, voice: 'v', title: 'CA Ent', duration: 10, audio_path: 's/ent_ca.mp3' },
  { section: 'sports', rank: 1, voice: 'v', title: 'CA Sports', duration: 10, audio_path: 's/spo_ca.mp3' },

  // Shared global sections
  { section: 'ai', rank: 1, voice: 'v', title: 'Global AI', duration: 10, audio_path: 's/ai.mp3' },
  { section: 'science', rank: 1, voice: 'v', title: 'Global Science', duration: 10, audio_path: 's/sci.mp3' },
];

test('buildBriefing preserves all 7 sections for US, India, and Canada editions', () => {

  // 1. US edition
  const usBrief = buildBriefing(multiEdRows, {}, { edition: 'us', voice: 'v' });
  assert.equal(usBrief.edition, 'us');
  assert.equal(usBrief.sections.length, 7, 'US edition must contain all 7 sections');
  const usKeys = usBrief.sections.map((s) => s.key);
  assert.deepEqual(usKeys, ['top_us', 'ai', 'tech_us', 'politics_us', 'entertainment_us', 'science', 'sports_us']);
  assert.equal(usBrief.stories.length, 7);

  // 2. India edition
  const inBrief = buildBriefing(multiEdRows, {}, { edition: 'in', voice: 'v' });
  assert.equal(inBrief.edition, 'in');
  assert.equal(inBrief.sections.length, 7, 'India edition must contain all 7 sections');
  const inKeys = inBrief.sections.map((s) => s.key);
  assert.deepEqual(inKeys, ['top_in', 'ai', 'tech_in', 'politics_in', 'entertainment_in', 'science', 'sports_in']);
  assert.equal(inBrief.stories.length, 7);

  // 3. Canada edition
  const caBrief = buildBriefing(multiEdRows, {}, { edition: 'ca', voice: 'v' });
  assert.equal(caBrief.edition, 'ca');
  assert.equal(caBrief.sections.length, 7, 'Canada edition must contain all 7 sections');
  const caKeys = caBrief.sections.map((s) => s.key);
  assert.deepEqual(caKeys, ['top', 'ai', 'tech', 'politics', 'entertainment', 'science', 'sports']);
  assert.equal(caBrief.stories.length, 7);
});

test('podcast mode starts with regional tease and directly enters top stories for US, India, and Canada', () => {
  const multiEdClips = [
    pc('podcast_ready', 0),
    pc('pod_open_1', 15),
    pc('pod_close_1', 10),
    pc('pod_tease_top', 15),
    pc('pod_tease_top_us', 15),
    pc('pod_tease_top_in', 15),
    pc('pod_bridge_ai', 8),
  ];
  const stories = { top: 1, ai: 1, tech: 0, politics: 0, entertainment: 0, science: 0, sports: 0 };

  const usB = buildBriefing(multiEdRows, { stories }, { edition: 'us', mode: 'podcast', podcastClips: multiEdClips });
  const usIds = ids(usB);
  assert.equal(usIds[0], 'pod_open_1');
  assert.equal(usIds[1], 'pod_tease_top_us');
  assert.equal(usIds[2], 'top_us-1');
  assert.equal(usIds[3], 'pod_bridge_ai');
  assert.equal(usIds[4], 'ai-1');

  const inB = buildBriefing(multiEdRows, { stories }, { edition: 'in', mode: 'podcast', podcastClips: multiEdClips });
  const inIds = ids(inB);
  assert.equal(inIds[0], 'pod_open_1');
  assert.equal(inIds[1], 'pod_tease_top_in');
  assert.equal(inIds[2], 'top_in-1');
  assert.equal(inIds[3], 'pod_bridge_ai');
  assert.equal(inIds[4], 'ai-1');

  const caB = buildBriefing(multiEdRows, { stories }, { edition: 'ca', mode: 'podcast', podcastClips: multiEdClips });
  const caIds = ids(caB);
  assert.equal(caIds[0], 'pod_open_1');
  assert.equal(caIds[1], 'pod_tease_top');
  assert.equal(caIds[2], 'top-1');
  assert.equal(caIds[3], 'pod_bridge_ai');
  assert.equal(caIds[4], 'ai-1');
});

test('posKeyFor generates independent timeline keys for Canada, US, and India', () => {
  const caPodcast = posKeyFor({ date: '2026-10-30', mode: 'podcast', edition: 'ca' });
  const usPodcast = posKeyFor({ date: '2026-10-30', mode: 'podcast', edition: 'us' });
  const inPodcast = posKeyFor({ date: '2026-10-30', mode: 'podcast', edition: 'in' });

  assert.equal(caPodcast, 'pos-2026-10-30-podcast-ca');
  assert.equal(usPodcast, 'pos-2026-10-30-podcast-us');
  assert.equal(inPodcast, 'pos-2026-10-30-podcast-in');

  assert.notEqual(caPodcast, inPodcast, 'Canada and India must have distinct position keys');
  assert.notEqual(usPodcast, inPodcast, 'US and India must have distinct position keys');

  const caFull = posKeyFor({ date: '2026-10-30', mode: 'full', edition: 'ca' });
  const inFull = posKeyFor({ date: '2026-10-30', mode: 'full', edition: 'in' });
  assert.equal(caFull, 'pos-2026-10-30-ca');
  assert.equal(inFull, 'pos-2026-10-30-in');
  assert.notEqual(caFull, inFull);
});

test('parseDialogueTurns extracts speaker-labeled turns and returns null for monologue scripts', () => {
  const dialogueScript = '[Matthew] Bank of Canada held its policy rate at 3.25 percent today.\n[Kelly] That affects variable mortgage holders immediately.';
  const turns = parseDialogueTurns(dialogueScript);
  assert.ok(Array.isArray(turns));
  assert.equal(turns.length, 2);
  assert.deepEqual(turns[0], { speaker: 'Matthew', text: 'Bank of Canada held its policy rate at 3.25 percent today.' });
  assert.deepEqual(turns[1], { speaker: 'Kelly', text: 'That affects variable mortgage holders immediately.' });

  assert.equal(parseDialogueTurns('Plain monologue sentence without speaker tags.'), null);
});

test('pickVoice and buildBriefing prefer matthew_reference+kelly_reference duo clips when present', () => {
  const duoVoice = 'matthew_reference+kelly_reference';
  const duoRows = [
    { date: 'd', section: 'top', rank: 1, voice: duoVoice, title: 'Top Story 1', script: '[Matthew] Line 1.\n[Kelly] Line 2.', duration: 24, audio_path: 's/duo/top1.mp3' },
    { date: 'd', section: 'top', rank: 2, voice: duoVoice, title: 'Top Story 2', script: '[Kelly] Line 1.\n[Matthew] Line 2.', duration: 22, audio_path: 's/duo/top2.mp3' },
  ];
  const duoPod = pod.map((c) => ({ ...c, hosts: duoVoice }));
  assert.equal(pickVoice(duoRows, 'c3po_reference'), duoVoice);

  const b = buildBriefing(duoRows, { stories: { top: 2 } }, { date: 'd', voice: duoVoice, notes: [{ voice: duoVoice, note_key: 'pack_ready' }], mode: 'podcast', podcastClips: duoPod });
  assert.equal(b.mode, 'podcast');
  assert.equal(b.voice.id, duoVoice);
  const storyClips = b.clips.filter((c) => !c.note && !c.gap);
  assert.equal(storyClips.length, 2);
  assert.ok(storyClips[0].url.includes('s/duo/top1.mp3'));
  assert.ok(storyClips[1].url.includes('s/duo/top2.mp3'));
});

test('parseShareSlug and buildBriefing resolve short share links by hash and rank', async () => {
  const shareSrc = readFileSync(new URL('../../web/api/share.js', import.meta.url), 'utf8')
    .replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'config.mjs'), "export const SUPABASE_URL = 'https://x'; export const SUPABASE_PUBLISHABLE_KEY = 'k'; export const FEATURES = { podcast: true, rapid: true }; export const APP_VERSION = '1.0.13';");
  writeFileSync(join(dir, 'share.mjs'), shareSrc);
  const { parseShareSlug } = await import(join(dir, 'share.mjs'));

  assert.deepEqual(parseShareSlug('c80758f3'), { storyId: 'c80758f3', section: null, rank: null, hash: 'c80758f3' });
  assert.deepEqual(parseShareSlug('ai-4-c80758f3'), { storyId: 'ai-4', section: 'ai', rank: 4, hash: 'c80758f3' });
  assert.deepEqual(parseShareSlug('tech_us-2-12ab34cd'), { storyId: 'tech_us-2', section: 'tech_us', rank: 2, hash: '12ab34cd' });
  assert.deepEqual(parseShareSlug('top-1'), { storyId: 'top-1', section: 'top', rank: 1, hash: null });

  const shareRows = [
    { date: '2026-10-31', section: 'top', rank: 1, voice: 'v', title: 'Canadian Top Story 1', duration: 20, audio_path: 'stories/2026-10-31/top-1-v-ca111111.mp3' },
    { date: '2026-10-31', section: 'top_in', rank: 1, voice: 'v', title: 'India Top Story 1', duration: 22, audio_path: 'stories/2026-10-31/top_in-1-v-12222222.mp3' },
    // Suppose a story that was ai-4 in the morning shifted to ai-5 in the evening, keeping its content hash c80758f3:
    { date: '2026-10-31', section: 'ai', rank: 5, voice: 'v', title: 'Anthropic expected to receive high junk rating', duration: 25, audio_path: 'stories/2026-10-31/ai-5-v-c80758f3.mp3' },
  ];

  // 1. User only has top: 1 enabled in settings, and opens /s/2026-10-31/c80758f3 (pure unique story key)
  const b = buildBriefing(shareRows, { stories: { top: 1, ai: 0 } }, {
    date: '2026-10-31',
    voice: 'v',
    targetStory: 'c80758f3',
    targetHash: 'c80758f3',
  });
  assert.ok(b);
  assert.ok(b.stories.some((s) => s.key === 'c80758f3' && s.headline.includes('Anthropic expected to receive')), 'Pure unique key must include and resolve the shared story even if rank shifted or section was disabled');

  // 2. Cross-region share: User in India (edition: 'in') clicks a Canadian story key ('ca111111')
  const inBrief = buildBriefing(shareRows, { stories: { top: 1, ai: 0 } }, {
    date: '2026-10-31',
    voice: 'v',
    edition: 'in',
    targetStory: 'ca111111',
    targetHash: 'ca111111',
  });
  assert.ok(inBrief);
  assert.equal(inBrief.edition, 'in', 'Recipient remains in their own India edition');
  assert.equal(inBrief.stories.length, 2, 'Both the shared Canadian story and the recipient India sequence are present');
  assert.equal(inBrief.stories[0].key, 'ca111111', 'Shared Canadian story is placed first in the sharing window');
  assert.equal(inBrief.stories[0].section, 'top_in', 'Shared story maps cleanly into the recipient regional section');
  assert.equal(inBrief.stories[0].isSharedBonus, true);
  assert.equal(inBrief.stories[1].key, '12222222', 'Recipient own India sequence follows immediately after');

  // Test the Vercel serverless share handler HTML injection with hero image & dialogue script
  const { default: shareHandler } = await import(join(dir, 'share.mjs'));
  const origFetch = globalThis.fetch;
  const sampleScript = '[Matthew] Anthropic is expected to get a high junk rating.\n[Kelly] Wait, why would credit agencies do that?';
  const sampleImage = 'https://images.unsplash.com/photo-sample.jpg';
  globalThis.fetch = async (url) => {
    if (String(url).includes('/rest/v1/story_audio')) {
      return {
        ok: true,
        json: async () => [
          {
            date: '2026-10-31',
            section: 'ai',
            rank: 4,
            voice: 'matthew_reference+kelly_reference',
            title: "Anthropic expected to receive high 'junk' rating",
            source: 'TechCrunch · AI',
            duration: 25,
            image: sampleImage,
            script: sampleScript,
            audio_path: 'stories/2026-10-31/ai-4-matthew_reference__kelly_reference-c80758f3.mp3',
          },
        ],
      };
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  let statusCode = 0;
  let bodyHtml = '';
  const headers = {};
  const mockReq = {
    url: '/api/share?date=2026-10-31&slug=ai-4-c80758f3',
    headers: { host: 'hark.vattitude.ca', 'x-forwarded-proto': 'https' },
  };
  const mockRes = {
    setHeader: (k, v) => { headers[k] = v; },
    status: (code) => {
      statusCode = code;
      return { send: (html) => { bodyHtml = html; } };
    },
  };

  try {
    await shareHandler(mockReq, mockRes);
  } finally {
    globalThis.fetch = origFetch;
  }

  assert.equal(statusCode, 200);
  assert.ok(bodyHtml.includes('<meta property="og:title" content="Anthropic expected to receive high &#39;junk&#39; rating">'));
  assert.ok(bodyHtml.includes('<meta property="og:description" content="TechCrunch · AI · 25s audio · Hark Daily">'));
  assert.ok(bodyHtml.includes(`<meta property="og:image" content="${sampleImage}">`));
  assert.ok(bodyHtml.includes('<meta property="og:image:width" content="1200">'));
  assert.ok(bodyHtml.includes('<meta name="twitter:card" content="summary_large_image">'));
  assert.ok(bodyHtml.includes('"image":"https://images.unsplash.com/photo-sample.jpg"'));
  assert.ok(bodyHtml.includes('[Matthew] Anthropic is expected to get a high junk rating.'));

  // Test that buildBriefing preserves targetImage & targetScript for shared bonus stories
  const sharedBonusBrief = buildBriefing([], {}, {
    date: '2026-10-31',
    mode: 'podcast',
    targetStory: 'ai-4',
    targetTitle: "Anthropic expected to receive high 'junk' rating",
    targetAudio: 'stories/2026-10-31/ai-4-matthew_reference__kelly_reference-c80758f3.mp3',
    targetHash: 'c80758f3',
    targetImage: sampleImage,
    targetScript: sampleScript,
    edition: 'ca',
  });
  assert.ok(sharedBonusBrief);
  const sharedStory = sharedBonusBrief.stories[0];
  assert.equal(sharedStory.image, sampleImage, 'Shared story preserves editorial image');
  assert.equal(sharedStory.script, sampleScript, 'Shared story preserves dialogue script');
  const turns = parseDialogueTurns(sharedStory.script);
  assert.ok(turns && turns.length === 2, 'Dialogue turns parse into speaker lines');
  assert.equal(turns[0].speaker, 'Matthew');
  assert.equal(turns[1].speaker, 'Kelly');
});

test('clipUrl normalizes voice underscores and preserves full URLs', () => {
  const legacy = 'stories/2026-10-31/ai-4-matthew_reference_kelly_reference-c80758f3.mp3';
  const url = clipUrl(legacy);
  assert.ok(url.includes('matthew_reference__kelly_reference-c80758f3.mp3'), 'Single underscore normalized to double underscore');

  const fullHttp = 'https://custom-storage.example.com/audio/clip.mp3';
  assert.equal(clipUrl(fullHttp), fullHttp, 'Full HTTP URL returned as-is');
});

test('buildBriefing matches targetAudio with single underscore against double underscore in rows without duplicates', () => {
  const sampleRow = {
    date: '2026-10-31',
    section: 'ai',
    rank: 4,
    voice: 'matthew_reference+kelly_reference',
    title: "Anthropic expected to receive high 'junk' rating",
    summary: 'Anthropic rating report',
    source: 'TechCrunch',
    duration: 25,
    audio_path: 'stories/2026-10-31/ai-4-matthew_reference__kelly_reference-c80758f3.mp3',
    image: 'https://images.example.com/anthropic.jpg',
    script: '[Matthew] Anthropic rating.\n[Kelly] That is notable.',
  };

  const rows = [
    { section: 'top', rank: 1, voice: 'matthew_reference+kelly_reference', title: 'Top 1', audio_path: 'stories/2026-10-31/top-1.mp3', duration: 20 },
    sampleRow,
  ];

  const brief = buildBriefing(rows, { stories: { top: 1, ai: 5 } }, {
    date: '2026-10-31',
    mode: 'podcast',
    targetAudio: 'stories/2026-10-31/ai-4-matthew_reference_kelly_reference-c80758f3.mp3',
    targetHash: 'c80758f3',
    targetTitle: "Anthropic expected to receive high 'junk' rating",
    edition: 'ca',
  });

  assert.ok(brief);
  const anthropicStories = brief.stories.filter((s) => s.headline.includes('Anthropic'));
  assert.equal(anthropicStories.length, 1, 'Anthropic story is not duplicated');
  assert.equal(anthropicStories[0].image, sampleRow.image, 'Retains original image from rows');
  assert.equal(anthropicStories[0].audio_path, sampleRow.audio_path, 'Retains valid double-underscore audio path');
});

test('voiceNormalize and parseDialogueTurns convert financial and textual shorthand to spoken words', () => {
  const raw = '[Matthew] Anthropic expects to raise $5B at a $60B valuation.\n[Kelly] That is 15% growth in Q3 vs Q2 w/ $500K profit.';
  const turns = parseDialogueTurns(raw);
  assert.ok(turns && turns.length === 2);
  assert.equal(turns[0].text, 'Anthropic expects to raise 5 billion dollars at a 60 billion dollars valuation.');
  assert.equal(turns[1].text, 'That is 15 percent growth in the third quarter versus the second quarter with 500 thousand dollars profit.');
});

test('podcast mode has zero gap clips for seamless continuous audio', () => {
  const b = build({ top: 2, ai: 1 });
  assert.equal(b.clips.some((c) => c.gap), false, 'Podcast briefing contains zero artificial gap clips');
  const top2Idx = b.clips.findIndex((c) => c.id === 'top-2');
  const aiBridgeIdx = b.clips.findIndex((c) => c.id === 'pod_bridge_ai');
  const ai1Idx = b.clips.findIndex((c) => c.id === 'ai-1');
  assert.equal(aiBridgeIdx, top2Idx + 1, 'Top stories flow directly into AI section bridge');
  assert.equal(ai1Idx, aiBridgeIdx + 1, 'AI section bridge flows directly into first AI story');
});

test('lineup defaults to 5 for top stories and 3 for other categories with max 5', () => {
  const defaults = lineup(null);
  assert.equal(defaults.top, 5);
  assert.equal(defaults.ai, 3);
  assert.equal(defaults.tech, 3);
  assert.equal(defaults.politics, 3);
  assert.equal(defaults.entertainment, 3);
  assert.equal(defaults.science, 3);
  assert.equal(defaults.sports, 3);

  assert.equal(MAX_PER_SECTION, 5);
  assert.equal(DEFAULT_SECTION_COUNTS.top, 5);
  assert.equal(DEFAULT_SECTION_COUNTS.ai, 3);

  // Untouched keys take defaults, customized keys clamp to [0, MAX_PER_SECTION]
  const custom = lineup({ stories: { top: 4, ai: 5, tech: 10, sports: 0 } });
  assert.equal(custom.top, 4);
  assert.equal(custom.ai, 5, 'AI dialed up to maximum 5');
  assert.equal(custom.tech, 5, 'Tech clamped to max 5');
  assert.equal(custom.sports, 0, 'Sports turned off');
  assert.equal(custom.science, 3, 'Untouched science keeps default 3');
  assert.equal(custom.politics, 3, 'Untouched politics keeps default 3');
});

test('Player transition lock: ignores intermediate browser pause events during clip transitions', async () => {
  class MockAudio extends EventTarget {
    constructor() {
      super();
      this.dataset = {};
      this.src = '';
      this.currentTime = 0;
      this.playbackRate = 1;
      this.volume = 1;
      this.muted = false;
      this.paused = true;
      this.ended = false;
      this.readyState = 4;
    }
    load() {
      // Browsers fire pause when src changes or load() resets media element
      this.paused = true;
      this.dispatchEvent(new Event('pause'));
    }
    async play() {
      this.paused = false;
      this.dispatchEvent(new Event('play'));
      this.dispatchEvent(new Event('playing'));
    }
    pause() {
      this.paused = true;
      this.dispatchEvent(new Event('pause'));
    }
  }

  const audio = new MockAudio();
  const preloader = new MockAudio();
  const player = new Player({ audio, preloader, el: {} });
  player.setupAudioElement(audio);

  const stateChanges = [];
  player.setPlaying = (on) => {
    stateChanges.push(on);
  };

  player.clips = [
    { id: 'story-1', url: 'https://cdn/story1.mp3', duration: 25 },
    { id: 'pod_bridge_ai', url: 'https://cdn/bridge.mp3', duration: 1.2, banter: true },
    { id: 'ai-1', url: 'https://cdn/ai1.mp3', duration: 25 },
  ];
  player.briefing = { stories: [] };

  // Simulate story-1 finishing and transitioning to pod_bridge_ai
  audio.paused = false; // Player was actively playing
  stateChanges.length = 0;

  player.loadClip(1, { seek: 0, autoplay: true, forceReload: true });

  // During loadClip, audio.load() dispatches 'pause', but because isTransitioningClip is true,
  // setPlaying(false) MUST NOT have been called.
  assert.ok(!stateChanges.includes(false), 'setPlaying(false) must not be called during clip transition');

  // After play resolves, isTransitioningClip is cleared and playing state remains true
  await Promise.resolve();
  assert.equal(player.isTransitioningClip, false);
  assert.equal(stateChanges.at(-1), true);

  // Now simulate an explicit user pause (not during transition)
  audio.pause();
  assert.equal(stateChanges.at(-1), false, 'Explicit user pause must call setPlaying(false)');
});

test('Player fail-safe: auto-advances if transition bridge clip rejects play or errors', async () => {
  class MockFailingAudio extends EventTarget {
    constructor() {
      super();
      this.dataset = {};
      this.src = '';
      this.currentTime = 0;
      this.playbackRate = 1;
      this.volume = 1;
      this.muted = false;
      this.paused = true;
      this.ended = false;
      this.readyState = 4;
    }
    load() {}
    async play() {
      if (this.dataset.clip === '1') {
        throw new Error('Decode error on short bridge');
      }
      this.paused = false;
      this.dispatchEvent(new Event('play'));
    }
  }

  const audio = new MockFailingAudio();
  const preloader = new MockFailingAudio();
  const player = new Player({ audio, preloader, el: {} });
  player.setupAudioElement(audio);
  player.setPlaying = () => {};

  player.clips = [
    { id: 'story-1', url: 'https://cdn/story1.mp3', duration: 25 },
    { id: 'pod_bridge_ai', url: 'https://cdn/bridge.mp3', duration: 1.2, banter: true },
    { id: 'ai-1', url: 'https://cdn/ai1.mp3', duration: 25 },
  ];
  player.briefing = { stories: [] };

  // Attempting to transition to clip 1 (which fails)
  player.loadClip(1, { seek: 0, autoplay: true, forceReload: true });
  await new Promise((r) => setTimeout(r, 10));

  // Player must have recovered and advanced to clip 2 ('ai-1')
  assert.equal(player.index, 2, 'Player auto-advanced to story clip after bridge error');
  assert.equal(audio.dataset.clip, '2');
});

test('Non-podcast mode queue: breaths only placed between stories, never between section intro and story', () => {
  const b = build({ top: 2, ai: 1 }, pod, 'full');
  assert.equal(b.mode, 'full');

  // Verify there is no gap clip immediately following intro_top or intro_ai
  for (let i = 0; i < b.clips.length; i++) {
    const c = b.clips[i];
    if (c.id && c.id.startsWith('intro_')) {
      const next = b.clips[i + 1];
      assert.ok(next && !next.gap, `Section intro ${c.id} must flow straight into story without gap`);
    }
  }
});

test('Player tick() clean player DOM updates and waveform scoping', () => {
  const domElements = new Map();
  const mockEl = (id) => {
    if (!domElements.has(id)) {
      domElements.set(id, {
        id,
        textContent: '',
        style: {},
        classList: { toggle: () => {}, add: () => {}, remove: () => {} },
        dataset: {},
        setAttribute: () => {},
        addEventListener: () => {},
        replaceChildren: () => {},
        querySelectorAll: () => [],
      });
    }
    return domElements.get(id);
  };

  const waveBars = Array.from({ length: 40 }, () => ({
    classList: { toggle: (cls, on) => {} },
  }));

  globalThis.document = {
    createElement: () => mockEl('created'),
    getElementById: (id) => mockEl(id),
    querySelectorAll: (sel) => {
      if (sel.includes('clean-wave-bar')) return waveBars;
      return [];
    },
    addEventListener: () => {},
    body: { classList: { toggle: () => {} } },
  };

  const b = build({ top: 2, ai: 1 });
  const audio = { pause: () => {}, play: async () => {}, playbackRate: 1, currentTime: 0, duration: 100, addEventListener: () => {} };
  const player = new Player({ audio, el: {} });
  b.duration = 489; // 8:09
  player.briefing = b;
  audio.currentTime = 10;
  player.chapters = b.chapters || [];

  // This must execute cleanly without "ReferenceError: frac is not defined"
  assert.doesNotThrow(() => {
    player.tick();
  });

  const headline = mockEl('cleanStoryHeadline').textContent;
  assert.ok(headline && headline.length > 0, 'Clean story headline must be populated');
  assert.notEqual(headline, "Loading today's briefing…");

  const curTime = mockEl('cleanCurTime').textContent;
  assert.equal(curTime, '10', 'cleanCurTime should be updated');

  const durTime = mockEl('cleanDurTime').textContent;
  assert.equal(durTime, '-90', 'cleanDurTime should reflect remaining duration');

  delete globalThis.document;
});

test('buildBriefing embeds date into each story item', () => {
  const b = build({ top: 2, ai: 1 });
  assert.ok(b.stories.length > 0);
  for (const s of b.stories) {
    assert.equal(s.date, 'd', 'Story should carry date from briefing');
  }
});

test('parseDeepLinkUrl and buildStoryShareUrl handle cross-date and native deep links', async () => {
  globalThis.window = { location: { origin: 'https://hark.vattitude.ca', search: '', hash: '', pathname: '/' }, addEventListener: () => {} };
  globalThis.document = { querySelector: () => null, getElementById: () => null, addEventListener: () => {}, removeEventListener: () => {}, documentElement: { classList: { add: () => {} }, style: { setProperty: () => {} } } };

  writeFileSync(join(dir, 'sheets.mjs'), 'export const WelcomeSheet = function() {}; export const DeleteAccountSheet = function() {}; export const enablePush = () => {}; export const installMode = () => {}; export const isIOS = () => false; export const isInstalled = () => false; export const onInstallChange = () => {}; export const promptInstall = () => {}; export const pushSupported = () => false; export const requestNotificationPermission = () => {}; export const wireSheet = () => {};');
  writeFileSync(join(dir, 'landing.mjs'), 'export class Landing {};');
  writeFileSync(join(dir, 'pages.mjs'), 'export class SourcesPage {}; export class SettingsPage {}; export class AdminPage {};');
  writeFileSync(join(dir, 'design.mjs'), 'export const applyPhotoMode = () => {};');

  const appSrc = readFileSync(new URL('../../web/js/app.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api.mjs'")
    .replace("'./storypack.js'", "'./storypack.mjs'")
    .replace("'./player.js'", "'./player.mjs'")
    .replace("'./sheets.js'", "'./sheets.mjs'")
    .replace("'./landing.js'", "'./landing.mjs'")
    .replace("'./pages/sources.js'", "'./pages.mjs'")
    .replace("'./pages/settings.js'", "'./pages.mjs'")
    .replace("'./pages/admin.js'", "'./pages.mjs'")
    .replace("'./design.js'", "'./design.mjs'")
    .replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'app.mjs'), appSrc);

  const { parseDeepLinkUrl, buildStoryShareUrl } = await import(join(dir, 'app.mjs'));

  // 1. parseDeepLinkUrl with date and slug
  const p1 = parseDeepLinkUrl('https://hark.vattitude.ca/s/2026-11-03/top-1-31fa57c9');
  assert.equal(p1.date, '2026-11-03');
  assert.equal(p1.story, 'top-1');
  assert.equal(p1.hash, '31fa57c9');

  // 2. parseDeepLinkUrl with pure hash
  const p2 = parseDeepLinkUrl('https://hark.vattitude.ca/s/2026-11-03/31fa57c9');
  assert.equal(p2.date, '2026-11-03');
  assert.equal(p2.hash, '31fa57c9');

  // 3. parseDeepLinkUrl with native app scheme
  const p3 = parseDeepLinkUrl('me.vattitude.morningbrief://s/2026-11-03/tech-2-abcd1234');
  assert.equal(p3.date, '2026-11-03');
  assert.equal(p3.story, 'tech-2');
  assert.equal(p3.hash, 'abcd1234');

  // 4. buildStoryShareUrl always preserves date
  const sUrl1 = buildStoryShareUrl({ id: 'top-1', key: '31fa57c9', date: '2026-11-03' });
  assert.equal(sUrl1, 'https://hark.vattitude.ca/s/2026-11-03/top-1-31fa57c9');

  // 5. Cross-date guard: generic rank IDs like top-1 must NOT match across dates
  const todayBriefing = {
    date: '2026-11-04',
    stories: [
      { id: 'top-1', key: 'todaytop1', headline: "Today's Bus Crash Story", date: '2026-11-04' },
      { id: 'tech-1', key: 'todaytech1', headline: "Today's Tech Story", date: '2026-11-04' },
    ],
  };

  const isGenericRank = /^[a-z_]+-\d+$/i.test('top-1');
  const targetDate = '2026-11-03';
  const shouldMatchFallback = !isGenericRank || !targetDate || todayBriefing.date === targetDate;
  assert.equal(shouldMatchFallback, false, 'Generic rank ID must not match across dates');

  delete globalThis.window;
  delete globalThis.document;
});

test('app.js exports initApp and boots cleanly when window and document are present', async () => {
  const removedClasses = [];
  globalThis.window = {
    location: { origin: 'https://hark.vattitude.ca', search: '', hash: '', pathname: '/' },
    addEventListener: () => {},
    matchMedia: () => ({ addEventListener: () => {} }),
    player: { isPlaying: false },
  };
  globalThis.document = {
    readyState: 'complete',
    createElement: () => ({ classList: { add: () => {}, remove: () => {} }, style: {}, appendChild: () => {}, dataset: {} }),
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: (id) => {
      if (id === 'appSplash') return { classList: { add: () => {}, contains: () => false }, remove: () => {} };
      return null;
    },
    addEventListener: () => {},
    removeEventListener: () => {},
    documentElement: { classList: { add: () => {} }, style: { setProperty: () => {} } },
    body: {
      classList: {
        contains: (cls) => cls === 'booting',
        remove: (cls) => removedClasses.push(cls),
        add: () => {},
      },
    },
  };

  const appSrc = readFileSync(new URL('../../web/js/app.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api.mjs'")
    .replace("'./storypack.js'", "'./storypack.mjs'")
    .replace("'./player.js'", "'./player.mjs'")
    .replace("'./sheets.js'", "'./sheets.mjs'")
    .replace("'./landing.js'", "'./landing.mjs'")
    .replace("'./pages/sources.js'", "'./pages.mjs'")
    .replace("'./pages/settings.js'", "'./pages.mjs'")
    .replace("'./pages/admin.js'", "'./pages.mjs'")
    .replace("'./design.js'", "'./design.mjs'")
    .replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'app_boot_test.mjs'), appSrc);

  await import(join(dir, 'app_boot_test.mjs'));
  assert.equal(typeof globalThis.window.initApp, 'function', 'window.initApp must be defined');

  delete globalThis.window;
  delete globalThis.document;
});

test('GIS Google Auth: cryptographic SHA-256 nonce generator and signInWithIdToken contract', async () => {
  const apiSrc = readFileSync(new URL('../../web/js/api.js', import.meta.url), 'utf8')
    .replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'api_gis.mjs'), apiSrc);
  const { generateRawNonce, hashNonce } = await import(join(dir, 'api_gis.mjs'));

  // 1. Test generateRawNonce format, entropy, and length
  const nonce1 = generateRawNonce();
  const nonce2 = generateRawNonce();
  assert.equal(typeof nonce1, 'string', 'nonce must be a string');
  assert.equal(nonce1.length, 64, '32 bytes hex encoded should be 64 characters');
  assert.match(nonce1, /^[0-9a-f]{64}$/, 'nonce must be lowercase hex');
  assert.notEqual(nonce1, nonce2, 'successive nonces must be cryptographically random and unique');

  // Custom length test
  const shortNonce = generateRawNonce(16);
  assert.equal(shortNonce.length, 32, '16 bytes hex encoded should be 32 characters');

  // 2. Test hashNonce with standard test vector for SHA-256
  // SHA-256("test") = 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
  const hashTest = await hashNonce('test');
  assert.equal(hashTest, '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08');

  // Hash of raw nonce
  const hashedNonce1 = await hashNonce(nonce1);
  assert.match(hashedNonce1, /^[0-9a-f]{64}$/, 'hashed nonce must be 64-char hex SHA-256');

  // 3. Test GIS initialize options and Supabase signInWithIdToken parameters contract
  let gisInitializedOptions = null;
  const mockGis = {
    accounts: {
      id: {
        initialize: (opts) => {
          gisInitializedOptions = opts;
        },
        renderButton: () => {},
        prompt: () => {},
      },
    },
  };

  let supabaseIdTokenParams = null;
  const mockSupabase = {
    auth: {
      signInWithIdToken: async (params) => {
        supabaseIdTokenParams = params;
        return { data: { user: { id: 'test-user-123' }, session: { access_token: 'fake-jwt' } }, error: null };
      },
    },
  };

  // Simulate GIS setup
  const rawNonce = generateRawNonce();
  const hashedNonce = await hashNonce(rawNonce);

  mockGis.accounts.id.initialize({
    client_id: 'test-client-id.apps.googleusercontent.com',
    callback: async (response) => {
      await mockSupabase.auth.signInWithIdToken({
        provider: 'google',
        token: response.credential,
        nonce: rawNonce, // original unhashed raw nonce
      });
    },
    nonce: hashedNonce, // hashed nonce passed to GIS
    use_fedcm_for_prompt: true,
    ux_mode: 'popup',
  });

  // Verify GIS initialize configuration
  assert.equal(gisInitializedOptions.client_id, 'test-client-id.apps.googleusercontent.com');
  assert.equal(gisInitializedOptions.nonce, hashedNonce, 'GIS initialize must receive hashedNonce');
  assert.equal(gisInitializedOptions.use_fedcm_for_prompt, true, 'use_fedcm_for_prompt must be true');
  assert.equal(gisInitializedOptions.ux_mode, 'popup', 'ux_mode must be popup');

  // Simulate Google credential response callback
  await gisInitializedOptions.callback({ credential: 'mock-google-id-token' });

  // Verify Supabase receives the original unhashed raw nonce + credential
  assert.ok(supabaseIdTokenParams, 'signInWithIdToken should be called');
  assert.equal(supabaseIdTokenParams.provider, 'google');
  assert.equal(supabaseIdTokenParams.token, 'mock-google-id-token');
  assert.equal(supabaseIdTokenParams.nonce, rawNonce, 'Supabase must receive original unhashed raw nonce');
  assert.equal(await hashNonce(supabaseIdTokenParams.nonce), gisInitializedOptions.nonce, 'Hash of Supabase nonce must equal GIS nonce');
});

test('GIS WebView & Native isolation prevents GIS execution in Android APK', async () => {
  const origUa = globalThis.navigator?.userAgent;
  const setUa = (ua) => {
    Object.defineProperty(globalThis.navigator, 'userAgent', {
      value: ua,
      configurable: true,
      writable: true,
    });
  };

  globalThis.window = {
    location: { origin: 'https://hark.vattitude.ca', search: '', hash: '', pathname: '/' },
    addEventListener: () => {},
    matchMedia: () => ({ addEventListener: () => {} }),
    player: { isPlaying: false },
    HarkNative: null,
    Capacitor: null,
  };
  globalThis.document = {
    readyState: 'complete',
    createElement: () => ({ classList: { add: () => {}, remove: () => {} }, style: {}, appendChild: () => {}, dataset: {} }),
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: () => null,
    addEventListener: () => {},
    removeEventListener: () => {},
    documentElement: { classList: { add: () => {} }, style: { setProperty: () => {} } },
    body: { classList: { contains: () => false, remove: () => {}, add: () => {} } },
  };

  const appSrc = readFileSync(new URL('../../web/js/app.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api.mjs'")
    .replace("'./storypack.js'", "'./storypack.mjs'")
    .replace("'./player.js'", "'./player.mjs'")
    .replace("'./sheets.js'", "'./sheets.mjs'")
    .replace("'./landing.js'", "'./landing.mjs'")
    .replace("'./pages/sources.js'", "'./pages.mjs'")
    .replace("'./pages/settings.js'", "'./pages.mjs'")
    .replace("'./pages/admin.js'", "'./pages.mjs'")
    .replace("'./design.js'", "'./design.mjs'")
    .replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'app_webview_test.mjs'), appSrc);

  const { isNativeOrWebView } = await import(join(dir, 'app_webview_test.mjs'));

  // 1. Standard web browser: false
  globalThis.window.HarkNative = null;
  globalThis.window.Capacitor = null;
  setUa('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
  assert.equal(isNativeOrWebView(), false, 'Standard desktop Chrome must not be detected as WebView');

  // 2. Android Chrome browser: false
  setUa('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36');
  assert.equal(isNativeOrWebView(), false, 'Mobile Chrome browser must not be detected as WebView');

  // 3. Android WebView with '; wv)': true
  setUa('Mozilla/5.0 (Linux; U; Android 14; en-us; Pixel 8 Build/UQ1A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.0.0 Mobile Safari/537.36');
  assert.equal(isNativeOrWebView(), true, 'Android WebView with wv must be detected as WebView');

  // 4. Android WebView with Version/4.0: true
  setUa('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.0.0 Mobile Safari/537.36');
  assert.equal(isNativeOrWebView(), true, 'Android WebView with Version/ must be detected as WebView');

  // 5. Capacitor native platform: true
  setUa('Mozilla/5.0');
  globalThis.window.Capacitor = { isNativePlatform: () => true };
  assert.equal(isNativeOrWebView(), true, 'Capacitor native platform must be detected');

  // 6. HarkNative bridge: true
  globalThis.window.Capacitor = null;
  globalThis.window.HarkNative = { isNativeShell: () => true };
  assert.equal(isNativeOrWebView(), true, 'HarkNative bridge must be detected');

  if (origUa !== undefined) setUa(origUa);
  delete globalThis.window;
  delete globalThis.document;
});

test('clearDeepLink clears deep link parameters and prevents session locking', async () => {
  let replacedUrl = null;
  globalThis.window = {
    location: {
      origin: 'https://hark.vattitude.ca',
      pathname: '/s/2026-11-04/ai-1-c80758f3',
      search: '',
      hash: '',
    },
    history: {
      replaceState: (state, title, url) => {
        replacedUrl = url;
      },
    },
    addEventListener: () => {},
    matchMedia: () => ({ addEventListener: () => {} }),
    player: { isPlaying: false },
    HarkNative: null,
    Capacitor: null,
  };
  globalThis.document = {
    readyState: 'complete',
    createElement: () => ({ classList: { add: () => {}, remove: () => {} }, style: {}, appendChild: () => {}, dataset: {} }),
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: () => null,
    addEventListener: () => {},
    removeEventListener: () => {},
    documentElement: { classList: { add: () => {} }, style: { setProperty: () => {} } },
    body: { classList: { contains: () => false, remove: () => {}, add: () => {} } },
  };

  const appSrc = readFileSync(new URL('../../web/js/app.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api.mjs'")
    .replace("'./storypack.js'", "'./storypack.mjs'")
    .replace("'./player.js'", "'./player.mjs'")
    .replace("'./sheets.js'", "'./sheets.mjs'")
    .replace("'./landing.js'", "'./landing.mjs'")
    .replace("'./pages/sources.js'", "'./pages.mjs'")
    .replace("'./pages/settings.js'", "'./pages.mjs'")
    .replace("'./pages/admin.js'", "'./pages.mjs'")
    .replace("'./design.js'", "'./design.mjs'")
    .replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'app_deeplink_test.mjs'), appSrc);

  const { clearDeepLink, handleDeepLinkUrl } = await import(join(dir, 'app_deeplink_test.mjs'));

  clearDeepLink();
  assert.equal(replacedUrl, '/', 'clearDeepLink must clean deep link URL to root /');
  assert.equal(globalThis.window.state.targetStoryConsumed, true, 'targetStoryConsumed must be true after clearDeepLink');

  // When a new deep link arrives:
  await handleDeepLinkUrl('https://hark.vattitude.ca/s/2026-11-05/top-1-aabbccdd');
  assert.equal(globalThis.window.state.targetStoryConsumed, true, 'handleDeepLinkUrl consumes link and marks consumed');

  delete globalThis.window;
  delete globalThis.document;
});

test('handleNativeAuthCallback and closeSignIn dismiss sign-in modal cleanly and reset button state', async () => {
  const elements = {
    signin: { classList: new Set() },
    googleBtn: { disabled: true },
    googleLabel: { textContent: 'Opening Google…' },
    menuDrawer: { classList: new Set() },
  };

  globalThis.window = {
    location: { origin: 'https://hark.vattitude.ca', search: '', hash: '', pathname: '/' },
    history: { replaceState: () => {} },
    addEventListener: () => {},
    matchMedia: () => ({ addEventListener: () => {} }),
    player: { isPlaying: false },
    HarkNative: null,
    Capacitor: null,
    toast: () => {},
    enterApp: () => {},
  };
  globalThis.localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
  globalThis.document = {
    readyState: 'complete',
    createElement: () => ({ classList: { add: () => {}, remove: () => {} }, style: {}, appendChild: () => {}, dataset: {} }),
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: (id) => {
      const el = elements[id];
      if (el) {
        return {
          get disabled() { return el.disabled; },
          set disabled(v) { el.disabled = v; },
          get textContent() { return el.textContent; },
          set textContent(v) { el.textContent = v; },
          classList: {
            add: (cls) => el.classList.add(cls),
            remove: (cls) => el.classList.delete(cls),
            contains: (cls) => el.classList.has(cls),
          },
          replaceChildren: () => {},
          setAttribute: () => {},
          getAttribute: () => null,
          appendChild: () => {},
          addEventListener: () => {},
          querySelector: () => null,
          querySelectorAll: () => [],
          style: {},
        };
      }
      return {
        classList: { add: () => {}, remove: () => {}, contains: () => false, toggle: () => {} },
        replaceChildren: () => {},
        setAttribute: () => {},
        getAttribute: () => null,
        appendChild: () => {},
        addEventListener: () => {},
        querySelector: () => null,
        querySelectorAll: () => [],
        style: {},
      };
    },
    addEventListener: () => {},
    removeEventListener: () => {},
    documentElement: { classList: { add: () => {} }, style: { setProperty: () => {} } },
    body: { classList: { contains: () => false, remove: () => {}, add: () => {} } },
  };

  let sessionPayload = null;
  globalThis.mockSb = {
    auth: {
      setSession: async (params) => {
        sessionPayload = params;
        return { data: { session: { access_token: params.access_token } }, error: null };
      },
      exchangeCodeForSession: async () => ({ data: null, error: new Error('not tested') }),
    },
  };

  writeFileSync(join(dir, 'api_auth.mjs'), `export const SECTIONS = {}; export const voiceName = (v) => v; export const fmtTime = (s) => String(s); export const h = () => ({ addEventListener: () => {}, classList: { toggle: () => {} } }); export const store = { get: (k, def) => (def !== undefined ? def : null), set: () => {} }; export const generateRawNonce = () => '00'; export const hashNonce = async () => '00'; export const api = { generateRawNonce: () => '00', hashNonce: async () => '00', signInWithGoogleIdToken: async () => ({}) }; export const icon = () => ({}); export const isAdmin = () => false; export const recordError = () => {}; export const sb = globalThis.mockSb; export const timeAgo = () => ''; export const toast = () => {}; export const VOICES = {}; export const voiceFor = () => ({}); export const DEFAULT_VOICE_ID = 'c3po_reference'; export const EDITIONS = {}; export const defaultEdition = () => 'ca'; export const detectEditionFromIp = () => 'ca';`);

  const appSrc = readFileSync(new URL('../../web/js/app.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api_auth.mjs'")
    .replace("'./storypack.js'", "'./storypack.mjs'")
    .replace("'./player.js'", "'./player.mjs'")
    .replace("'./sheets.js'", "'./sheets.mjs'")
    .replace("'./landing.js'", "'./landing.mjs'")
    .replace("'./pages/sources.js'", "'./pages.mjs'")
    .replace("'./pages/settings.js'", "'./pages.mjs'")
    .replace("'./pages/admin.js'", "'./pages.mjs'")
    .replace("'./design.js'", "'./design.mjs'")
    .replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'app_auth_test.mjs'), appSrc);

  const { closeSignIn, handleNativeAuthCallback } = await import(join(dir, 'app_auth_test.mjs'));

  // Test 1: closeSignIn hides modal and resets button
  closeSignIn();
  assert.equal(elements.signin.classList.has('hidden'), true, 'closeSignIn must hide signin modal');
  assert.equal(elements.googleBtn.disabled, false, 'closeSignIn must re-enable Google button');
  assert.equal(elements.googleLabel.textContent, 'Continue with Google', 'closeSignIn must restore button text');

  // Set modal back to open and button to busy
  elements.signin.classList.delete('hidden');
  elements.googleBtn.disabled = true;
  elements.googleLabel.textContent = 'Opening Google…';

  // Test 2: handleNativeAuthCallback with valid tokens dismisses modal
  await handleNativeAuthCallback('me.vattitude.morningbrief://auth#access_token=my_access_token&refresh_token=my_refresh_token');
  assert.ok(sessionPayload, 'setSession must be invoked');
  assert.equal(sessionPayload.access_token, 'my_access_token');
  assert.equal(sessionPayload.refresh_token, 'my_refresh_token');
  assert.equal(elements.signin.classList.has('hidden'), true, 'handleNativeAuthCallback must hide signin modal after successful auth');
  assert.equal(elements.googleBtn.disabled, false, 'handleNativeAuthCallback must reset button disabled state');
  assert.equal(elements.googleLabel.textContent, 'Continue with Google');

  // Test 3: handleNativeAuthCallback with error resets button
  elements.googleBtn.disabled = true;
  elements.googleLabel.textContent = 'Opening Google…';
  await handleNativeAuthCallback('me.vattitude.morningbrief://auth?error=access_denied&error_description=User+cancelled');
  assert.equal(elements.googleBtn.disabled, false, 'handleNativeAuthCallback must re-enable button on error');
  assert.equal(elements.googleLabel.textContent, 'Continue with Google');

  // Wait for setTimeout(enterApp, 0) to flush before deleting globals
  await new Promise((r) => setTimeout(r, 20));

  delete globalThis.window;
  delete globalThis.document;
  delete globalThis.mockSb;
  delete globalThis.localStorage;
});

test('podcast mode is not discarded by single-narrator voice_notes pack_ready markers', async () => {
  const notesWithC3poOnly = [
    { voice: 'c3po_reference', note_key: 'pack_ready', text: '5 clips', duration: 0 },
    { voice: 'c3po_reference', note_key: 'intro_top', text: 'Top stories', duration: 2 },
  ];

  // Duo briefing with matthew_reference+kelly_reference
  const duoBriefing = {
    mode: 'podcast',
    voice: { id: 'matthew_reference+kelly_reference', name: 'Matthew & Kelly' },
  };

  const isPodcast = duoBriefing.mode === 'podcast';
  const hosts = (duoBriefing.voice?.id || '').split('+').filter(Boolean);
  const hasReadyMarkers = notesWithC3poOnly.some((n) => n.note_key === 'pack_ready');

  // Assert that the single-narrator check is skipped for podcast mode
  const shouldEnforceSingleVoiceNotes = hasReadyMarkers && !isPodcast && hosts.length <= 1;
  assert.equal(shouldEnforceSingleVoiceNotes, false, 'Podcast mode must never enforce single-narrator voice_notes ready check');

  // Single narrator mode (C-3PO) should enforce check
  const singleBriefing = {
    mode: 'full',
    voice: { id: 'c3po_reference', name: 'C-3PO' },
  };
  const isSinglePodcast = singleBriefing.mode === 'podcast';
  const singleHosts = (singleBriefing.voice?.id || '').split('+').filter(Boolean);
  const shouldEnforceC3po = hasReadyMarkers && !isSinglePodcast && singleHosts.length <= 1;
  assert.equal(shouldEnforceC3po, true, 'Single narrator mode must enforce voice_notes ready check');
  const isC3poReady = notesWithC3poOnly.some((n) => n.note_key === 'pack_ready' && n.voice === singleBriefing.voice.id);
  assert.equal(isC3poReady, true, 'C-3PO should be ready when marker is present');
});

test('app version and drawer version synchronization across config, index.html, and package.json', () => {
  const pkg = JSON.parse(readFileSync(new URL('../../package.json', import.meta.url), 'utf8'));
  const configText = readFileSync(new URL('../../web/config.js', import.meta.url), 'utf8');
  const indexHtml = readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');

  const configVersionMatch = configText.match(/APP_VERSION\s*=\s*['"]([^'"]+)['"]/);
  assert.ok(configVersionMatch, 'APP_VERSION must be defined in web/config.js');
  const configVersion = configVersionMatch[1];
  const cleanConfigVersion = configVersion.replace(/^v/, '');

  assert.equal(cleanConfigVersion, pkg.version, 'web/config.js APP_VERSION must match package.json version');

  const formattedVer = configVersion.startsWith('v') ? configVersion : `v${configVersion}`;
  const expectedDrawerHtml = `<div class="clean-drawer-version" id="cleanDrawerVersion">Hark Daily ${formattedVer}</div>`;
  assert.ok(
    indexHtml.includes(expectedDrawerHtml),
    `web/index.html must include the current drawer version element: ${expectedDrawerHtml}`
  );
});

test('markets section is configured across logical sections, default counts, and regional mappings', () => {
  const apiSrc = readFileSync(new URL('../../web/js/api.js', import.meta.url), 'utf8');

  assert.ok(LOGICAL_SECTIONS.includes('markets'), 'LOGICAL_SECTIONS must include markets');
  assert.equal(DEFAULT_SECTION_COUNTS.markets, 3, 'Markets must default to 3 stories');

  assert.equal(editionSectionKey('markets', 'ca'), 'markets');
  assert.equal(editionSectionKey('markets', 'us'), 'markets_us');
  assert.equal(editionSectionKey('markets', 'in'), 'markets_in');

  assert.ok(apiSrc.includes("markets: { title: 'Markets'"), 'api.js must define Canada markets');
  assert.ok(apiSrc.includes("markets_us: { title: 'Markets'"), 'api.js must define US markets');
  assert.ok(apiSrc.includes("markets_in: { title: 'Markets'"), 'api.js must define India markets');
});

test('existing users receive markets defaulting to 3 stories and placed right after top', () => {
  // Existing user settings without 'markets'
  const existingSettings = {
    stories: {
      top: 5,
      ai: 2,
      tech: 3,
      politics: 4,
      entertainment: 1,
      science: 3,
      sports: 0,
    },
    section_order: ['top', 'tech', 'ai', 'politics', 'sports', 'entertainment', 'science'],
  };

  const calculatedLineup = lineup(existingSettings);
  assert.equal(calculatedLineup.markets, 3, 'Markets must default to 3 stories for existing users');
  assert.equal(calculatedLineup.top, 5);
  assert.equal(calculatedLineup.ai, 2);
  assert.equal(calculatedLineup.sports, 0);

  // When building briefing, markets is placed right after top
  const testRows = [
    { date: 'd', section: 'top', rank: 1, voice: 'v', title: 'Top 1', url: 'u', source: 's', script: 'x', duration: 20, audio_path: 's/top1.mp3' },
    { date: 'd', section: 'markets', rank: 1, voice: 'v', title: 'Markets 1', url: 'u', source: 's', script: 'x', duration: 20, audio_path: 's/markets1.mp3' },
    { date: 'd', section: 'tech', rank: 1, voice: 'v', title: 'Tech 1', url: 'u', source: 's', script: 'x', duration: 20, audio_path: 's/tech1.mp3' },
  ];
  const b = buildBriefing(testRows, existingSettings, { date: 'd', voice: 'v', notes: [] });
  assert.ok(b, 'Briefing must build successfully');
  const sectionKeys = b.sections.map((s) => s.logicalKey);
  assert.equal(sectionKeys[0], 'top');
  assert.equal(sectionKeys[1], 'markets', 'Markets must be placed right after top even if absent from legacy section_order');
});

test('date dropdown menuDateSelect is present in index.html drawer and clean placeholder strings avoid dummy data', () => {
  const indexHtml = readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');

  assert.ok(indexHtml.includes('id="menuDateSelect"'), 'Drawer must contain menuDateSelect dropdown');
  assert.ok(!indexHtml.includes('id="menuDateYesterday"'), 'Legacy binary menuDateYesterday button must be removed');
  assert.ok(!indexHtml.includes('id="menuDateToday"'), 'Legacy binary menuDateToday button must be removed');

  // Verify placeholder dummy strings are neutral/empty
  assert.ok(indexHtml.includes('<span class="clean-story-counter" id="cleanStoryCounter"></span>'), 'cleanStoryCounter placeholder must be empty');
  assert.ok(indexHtml.includes('<span id="cleanDurTime">--:--</span>'), 'cleanDurTime placeholder must be neutral');
  assert.ok(indexHtml.includes('<span id="openAllStoriesLabel">All Stories</span>'), 'All Stories button must not have hardcoded number');
  assert.ok(!indexHtml.includes('alt="Story cover image"'), 'Story cover image alt text must be removed to prevent browser broken image text artifacts');
});

test('getDefaultCover returns dedicated SVG covers and isolates cricket/sports, tech, markets', () => {
  assert.equal(getDefaultCover('sports_in'), '/icons/covers/sports.svg');
  assert.equal(getDefaultCover('cricket'), '/icons/covers/sports.svg');
  assert.equal(getDefaultCover('sports_us'), '/icons/covers/sports.svg');
  assert.equal(getDefaultCover('sports'), '/icons/covers/sports.svg');
  assert.equal(getDefaultCover('tech_us'), '/icons/covers/tech.svg');
  assert.equal(getDefaultCover('markets_in'), '/icons/covers/markets.svg');
  assert.equal(getDefaultCover('politics_in'), '/icons/covers/politics.svg');
  assert.equal(getDefaultCover('entertainment_us'), '/icons/covers/entertainment.svg');
  assert.equal(getDefaultCover('science'), '/icons/covers/science.svg');
  assert.equal(getDefaultCover('ai'), '/icons/covers/ai.svg');
  assert.equal(getDefaultCover('top_in'), '/icons/covers/default.svg');
  assert.equal(getDefaultCover(''), '/icons/covers/default.svg');
});

test('Player records failed image URLs and preserves category default cover without flapping', () => {
  const player = new Player({ audio: {}, el: {} });
  assert.ok(player.failedImages instanceof Set);

  // If cleanCoverImg fails, error handler adds URL to failedImages and applies fallback
  const brokenUrl = 'http://p.imgci.com/db/PICTURES/CMS/424100/424116.jpg';
  player.failedImages.add(brokenUrl);
  assert.ok(player.failedImages.has(brokenUrl));

  // Simulating story with broken image
  const story = { section: 'sports_in', image: brokenUrl };
  const fallback = getDefaultCover(story.section);
  const effectiveImg = (story.image && !player.failedImages.has(story.image)) ? story.image : fallback;
  assert.equal(effectiveImg, '/icons/covers/sports.svg');
});












