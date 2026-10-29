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
const { EDITIONS, defaultEdition, detectEditionFromIp } = await import(join(dir, 'api.mjs'));

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
