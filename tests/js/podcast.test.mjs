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
writeFileSync(join(dir, 'api.mjs'), "export const SECTIONS = { top: { title: 'Top' }, ai: { title: 'AI' }, tech: { title: 'Tech' }, sports: { title: 'Sports' } }; export const voiceName = (v) => v;");
writeFileSync(join(dir, 'config.mjs'), "export const SUPABASE_URL = 'https://x';");
const { buildBriefing, planPodcast, PODCAST_BUDGET } = await import(join(dir, 'storypack.mjs'));

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
