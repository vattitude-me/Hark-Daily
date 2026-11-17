import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

const dir = mkdtempSync(join(tmpdir(), 'preprod-config-'));
const src = readFileSync(new URL('../../web/config.js', import.meta.url), 'utf8');
writeFileSync(join(dir, 'config.mjs'), src);
const {
  isPreprodHost,
  resolveSupabaseConfig,
  SUPABASE_URL,
  SUPABASE_PUBLISHABLE_KEY,
  IS_PREPROD,
} = await import(join(dir, 'config.mjs'));

const PROD_URL = 'https://oohbmeffdncyzujmeqcz.supabase.co';
const PREPROD_URL = 'https://hhcygubulddewtwkedkz.supabase.co';
const PREPROD_KEY = 'sb_publishable_8vYLo4tLmmKDbThLnLKatA_7xBhV2jC';

test('resolveSupabaseConfig pins production host and VERCEL_ENV=production to prod Supabase', () => {
  const prod = resolveSupabaseConfig({ hostname: 'hark.vattitude.ca', env: { VERCEL_ENV: 'production' } });
  assert.equal(prod.url, PROD_URL);
  assert.equal(prod.isPreprod, false);

  const bareDefault = resolveSupabaseConfig({ hostname: '', env: {} });
  assert.equal(bareDefault.url, PROD_URL);
  assert.equal(bareDefault.isPreprod, false);
  assert.equal(SUPABASE_URL, PROD_URL);
  assert.ok(SUPABASE_PUBLISHABLE_KEY.startsWith('sb_publishable_'));
  assert.equal(IS_PREPROD, false);
});

test('isPreprodHost and resolveSupabaseConfig route local, preview, and dev hosts to pre-prod Supabase', () => {
  for (const host of ['localhost', '127.0.0.1', 'hark-daily-git-dev.vercel.app', 'preprod.hark.vattitude.ca', 'dev.hark.vattitude.ca']) {
    assert.equal(isPreprodHost(host), true, `Expected ${host} to match pre-prod`);
    const cfg = resolveSupabaseConfig({ hostname: host, env: {} });
    assert.equal(cfg.url, PREPROD_URL);
    assert.equal(cfg.publishableKey, PREPROD_KEY);
    assert.equal(cfg.isPreprod, true);
  }

  for (const vercelEnv of ['preview', 'development']) {
    const cfg = resolveSupabaseConfig({ hostname: '', env: { VERCEL_ENV: vercelEnv } });
    assert.equal(cfg.url, PREPROD_URL);
    assert.equal(cfg.publishableKey, PREPROD_KEY);
    assert.equal(cfg.isPreprod, true);
  }
});

test('resolveSupabaseConfig honors explicit SUPABASE_URL and key env overrides', () => {
  const custom = resolveSupabaseConfig({
    hostname: 'hark.vattitude.ca',
    env: { SUPABASE_URL: 'https://custom.supabase.co/', SUPABASE_ANON_KEY: 'custom_anon_key' },
  });
  assert.equal(custom.url, 'https://custom.supabase.co');
  assert.equal(custom.publishableKey, 'custom_anon_key');
  assert.equal(custom.isPreprod, true);
});
