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
  ai: { title: 'AI' }, tech: { title: 'Tech' }, science: { title: 'Science' },
  politics: { title: 'Politics' }, politics_us: { title: 'Politics' }, politics_in: { title: 'Politics' },
  entertainment: { title: 'Entertainment' }, entertainment_us: { title: 'Entertainment' }, entertainment_in: { title: 'Entertainment' },
  sports: { title: 'Sports' }, sports_us: { title: 'Sports' }, sports_in: { title: 'Cricket & Sports' }
}; export const voiceName = (v) => v;`);
writeFileSync(join(dir, 'config.mjs'), "export const SUPABASE_URL = 'https://x';");
const { buildBriefing, planPodcast, PODCAST_BUDGET, editionSectionKey, clipsFor } = await import(join(dir, 'storypack.mjs'));

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

test('podcast brief: open, teasers, bridges before stories, close; no narrator intros', () => {
  const b = build({ top: 2, ai: 1 });
  assert.equal(b.mode, 'podcast');
  const list = ids(b);
  assert.match(list[0], /^pod_open_/);
  assert.match(list.at(-1), /^pod_close_/);
  assert.ok(list.indexOf('pod_bridge_top') < list.indexOf('top-1'));
  assert.ok(list.indexOf('pod_bridge_ai') < list.indexOf('ai-1'));
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
  const list = ids(build({ top: 2, ai: 1 }));
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
  assert.equal(editionSectionKey('tech', 'in'), 'tech');
  assert.equal(editionSectionKey('science', 'us'), 'science');
});

test('clipsFor selects edition-specific clips and falls back to base if unavailable', () => {
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
  // Since top_in is missing in mixedRows, it cleanly falls back to top (CA Top)
  assert.equal(inClips.length, 2);
  assert.equal(inClips[0].title, 'CA Top');
  assert.equal(inClips[1].title, 'Global AI');
});

test('buildBriefing preserves all 7 sections for US, India, and Canada editions', () => {
  const multiEdRows = [
    // US sections
    { section: 'top_us', rank: 1, voice: 'v', title: 'US Top', duration: 10, audio_path: 's/top_us.mp3' },
    { section: 'politics_us', rank: 1, voice: 'v', title: 'US Politics', duration: 10, audio_path: 's/pol_us.mp3' },
    { section: 'entertainment_us', rank: 1, voice: 'v', title: 'US Ent', duration: 10, audio_path: 's/ent_us.mp3' },
    { section: 'sports_us', rank: 1, voice: 'v', title: 'US Sports', duration: 10, audio_path: 's/spo_us.mp3' },

    // India sections
    { section: 'top_in', rank: 1, voice: 'v', title: 'IN Top', duration: 10, audio_path: 's/top_in.mp3' },
    { section: 'politics_in', rank: 1, voice: 'v', title: 'IN Politics', duration: 10, audio_path: 's/pol_in.mp3' },
    { section: 'entertainment_in', rank: 1, voice: 'v', title: 'IN Ent', duration: 10, audio_path: 's/ent_in.mp3' },
    { section: 'sports_in', rank: 1, voice: 'v', title: 'IN Cricket', duration: 10, audio_path: 's/spo_in.mp3' },

    // Canada sections
    { section: 'top', rank: 1, voice: 'v', title: 'CA Top', duration: 10, audio_path: 's/top_ca.mp3' },
    { section: 'politics', rank: 1, voice: 'v', title: 'CA Politics', duration: 10, audio_path: 's/pol_ca.mp3' },
    { section: 'entertainment', rank: 1, voice: 'v', title: 'CA Ent', duration: 10, audio_path: 's/ent_ca.mp3' },
    { section: 'sports', rank: 1, voice: 'v', title: 'CA Sports', duration: 10, audio_path: 's/spo_ca.mp3' },

    // Shared global sections
    { section: 'ai', rank: 1, voice: 'v', title: 'Global AI', duration: 10, audio_path: 's/ai.mp3' },
    { section: 'tech', rank: 1, voice: 'v', title: 'Global Tech', duration: 10, audio_path: 's/tech.mp3' },
    { section: 'science', rank: 1, voice: 'v', title: 'Global Science', duration: 10, audio_path: 's/sci.mp3' },
  ];

  // 1. US edition
  const usBrief = buildBriefing(multiEdRows, {}, { edition: 'us', voice: 'v' });
  assert.equal(usBrief.sections.length, 7, 'US edition must contain all 7 sections');
  const usKeys = usBrief.sections.map((s) => s.key);
  assert.deepEqual(usKeys, ['top_us', 'ai', 'tech', 'politics_us', 'entertainment_us', 'science', 'sports_us']);
  assert.equal(usBrief.stories.length, 7);

  // 2. India edition
  const inBrief = buildBriefing(multiEdRows, {}, { edition: 'in', voice: 'v' });
  assert.equal(inBrief.sections.length, 7, 'India edition must contain all 7 sections');
  const inKeys = inBrief.sections.map((s) => s.key);
  assert.deepEqual(inKeys, ['top_in', 'ai', 'tech', 'politics_in', 'entertainment_in', 'science', 'sports_in']);
  assert.equal(inBrief.stories.length, 7);

  // 3. Canada edition
  const caBrief = buildBriefing(multiEdRows, {}, { edition: 'ca', voice: 'v' });
  assert.equal(caBrief.sections.length, 7, 'Canada edition must contain all 7 sections');
  const caKeys = caBrief.sections.map((s) => s.key);
  assert.deepEqual(caKeys, ['top', 'ai', 'tech', 'politics', 'entertainment', 'science', 'sports']);
  assert.equal(caBrief.stories.length, 7);
});

