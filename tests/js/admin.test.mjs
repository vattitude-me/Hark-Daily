import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const dir = mkdtempSync(join(tmpdir(), 'admin-test-'));

// Mock config
writeFileSync(join(dir, 'config.mjs'), "export const SUPABASE_URL = 'https://x'; export const SUPABASE_PUBLISHABLE_KEY = 'k';");

// Mock design
writeFileSync(join(dir, 'design.mjs'), `
export const Overline = (t) => ({ type: 'overline', text: t });
export const Hint = (t) => ({ type: 'hint', text: t });
export const Hairline = () => ({ type: 'hairline' });
export const GlassGroup = (...c) => ({ type: 'glass-group', children: c });
export const SectionLabel = (t, o) => ({ type: 'section-label', text: t, ...o });
export const ListRow = (o) => ({ type: 'list-row', ...o });
export const CheckDot = (c) => ({ type: 'check-dot', checked: c });
export const SwitchRow = (l, c, o) => ({ type: 'switch-row', label: l, checked: c, ...o });
export const Tag = (t, s) => ({ type: 'tag', text: t, style: s });
export const PillButton = (l, o) => ({ type: 'pill-button', label: l, ...o });
`);

// Mock storypack
writeFileSync(join(dir, 'storypack.mjs'), `
export const READY_KEY = 'pack_ready';
export const clipUrl = (path) => path ? \`https://cdn.hark.ca/\${path}\` : '';
`);

// Setup api.mjs
const apiSrc = readFileSync(new URL('../../web/js/api.js', import.meta.url), 'utf8')
  .replace("'../config.js'", "'./config.mjs'");
writeFileSync(join(dir, 'api.mjs'), apiSrc);
const { isAdmin, ADMIN_EMAILS } = await import(join(dir, 'api.mjs'));

// Setup admin.mjs
const adminSrc = readFileSync(new URL('../../web/js/pages/admin.js', import.meta.url), 'utf8')
  .replace("'../api.js'", "'./api.mjs'")
  .replace("'../storypack.js'", "'./storypack.mjs'")
  .replace("'../design.js'", "'./design.mjs'");
writeFileSync(join(dir, 'admin.mjs'), adminSrc);

const {
  AdminPage,
  formatExecutiveRunReport,
  minutes,
  dayLabel,
  today,
  EDITION_DEFS,
} = await import(join(dir, 'admin.mjs'));

test('isAdmin security gate checks admin privileges', () => {
  assert.equal(isAdmin(null), false);
  assert.equal(isAdmin({}), false);
  assert.equal(isAdmin({ email: 'user@example.com' }), false);
  assert.equal(isAdmin({ email: 'User@Example.Com', is_admin: false }), false);

  // Custom is_admin flag
  assert.equal(isAdmin({ is_admin: true, email: 'custom@hark.ca' }), true);
  assert.equal(isAdmin({ is_admin: true }), true);

  // Configured ADMIN_EMAILS allowlist
  ADMIN_EMAILS.push('admin@hark.ca');
  assert.equal(isAdmin({ email: 'admin@hark.ca' }), true);
  assert.equal(isAdmin({ email: 'Admin@Hark.Ca' }), true);
  ADMIN_EMAILS.pop();
});

test('minutes formatter correctly formats seconds and minutes', () => {
  assert.equal(minutes(0), '0s');
  assert.equal(minutes(45), '45s');
  assert.equal(minutes(59), '59s');
  assert.equal(minutes(60), '1.0 min');
  assert.equal(minutes(150), '2.5 min');
  assert.equal(minutes(3600), '60.0 min');
});

test('dayLabel identifies today, yesterday, and past dates', () => {
  const t = today();
  assert.equal(dayLabel(t), 'Today');

  const y = new Date();
  y.setDate(y.getDate() - 1);
  const yStr = y.toLocaleDateString('en-CA');
  assert.equal(dayLabel(yStr), 'Yesterday');
});

test('formatExecutiveRunReport produces structured summary for WhatsApp/Email', () => {
  const mockPack = {
    clips: [
      { section: 'top', rank: 1, duration: 65, voice: 'matthew_reference+kelly_reference' },
      { section: 'ai', rank: 1, duration: 80, voice: 'matthew_reference+kelly_reference' },
      { section: 'tech', rank: 1, duration: 75, voice: 'matthew_reference+kelly_reference' },
      { section: 'top_us', rank: 1, duration: 70, voice: 'matthew_reference+kelly_reference' },
      { section: 'top_in', rank: 1, duration: 60, voice: 'matthew_reference+kelly_reference' },
    ],
    notes: [{ note_key: 'pack_ready', duration: 0, voice: 'matthew_reference+kelly_reference' }],
    podcastClips: [
      { clip_key: 'pod_open_v1', duration: 18 },
      { clip_key: 'pod_bridge_ai', duration: 4 },
      { clip_key: 'pod_close_v1', duration: 12 },
    ],
  };

  const mockLog = [
    {
      run_date: '2026-11-03',
      status: 'ok',
      title: '✓ Morning Brief ready',
      detail: 'Took 3m 42s · 18 stories built',
    },
  ];

  const report = formatExecutiveRunReport({
    day: '2026-11-03',
    status: { running: false },
    pack: mockPack,
    log: mockLog,
  });

  assert.match(report, /HARK DAILY — PIPELINE RUN REPORT/);
  assert.match(report, /ALL SYSTEMS NOMINAL/);
  assert.match(report, /Canada Edition \(CA\)/);
  assert.match(report, /United States Edition \(US\)/);
  assert.match(report, /India Edition \(IN\)/);
  assert.match(report, /Matthew & Kelly/);
  assert.match(report, /Framing Clips: 3 segments/);
  assert.match(report, /Took 3m 42s/);
  assert.match(report, /https:\/\/hark\.vattitude\.ca\//);
});

test('AdminPage initializes with expected defaults and switches tabs', () => {
  const dummyRoot = {
    replaceChildren: () => {},
  };
  const admin = new AdminPage({ root: dummyRoot });
  assert.equal(admin.activeTab, 'overview');
  assert.equal(admin.edition, 'all');
  assert.equal(admin.rebuildScope, 'framing');

  let stopped = false;
  admin.stopPreview = () => { stopped = true; };
  admin.render = () => {};

  admin.switchTab('reports');
  assert.equal(admin.activeTab, 'reports');
  assert.equal(stopped, true);

  admin.switchTab('editions');
  assert.equal(admin.activeTab, 'editions');

  admin.switchTab('operations');
  assert.equal(admin.activeTab, 'operations');

  admin.switchTab('diagnostics');
  assert.equal(admin.activeTab, 'diagnostics');
});

test('EDITION_DEFS provides full coverage across Canada, US, and India', () => {
  assert.equal(EDITION_DEFS.length, 3);
  const codes = EDITION_DEFS.map((e) => e.code);
  assert.deepEqual(codes, ['CA', 'US', 'IN']);

  for (const ed of EDITION_DEFS) {
    assert.ok(ed.sections.length >= 7, `${ed.name} must cover at least 7 sections`);
    assert.ok(ed.flag, `${ed.name} must have a country flag`);
  }
});
