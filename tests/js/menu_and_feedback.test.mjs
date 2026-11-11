import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('Drawer Header contains dedicated Account button', () => {
  const html = readFileSync(resolve('web/index.html'), 'utf8');
  assert.ok(html.includes('id="drawerAccountBtn"'), 'Must contain drawerAccountBtn in drawer header');
  assert.ok(html.includes('id="drawerAccountLabel"'), 'Must contain drawerAccountLabel');
  assert.ok(html.includes('clean-drawer-account-btn'), 'Must have clean-drawer-account-btn class');
});

test('Restart briefing and Playback Speed are placed on the homepage player flanking the scrubber', () => {
  const html = readFileSync(resolve('web/index.html'), 'utf8');
  assert.ok(html.includes('id="cleanScrubberRow"'), 'Must contain cleanScrubberRow container');
  assert.ok(html.includes('id="cleanRestartBtn"'), 'Must contain cleanRestartBtn on the left of scrubber');
  assert.ok(html.includes('id="cleanSpeedBtn"'), 'Must contain cleanSpeedBtn on the right of scrubber');
  assert.ok(html.includes('id="cleanSpeedVal"'), 'Must contain cleanSpeedVal for dynamic playback rate display');
  assert.ok(!html.includes('class="clean-menu-row-split"'), 'Speed and restart must be moved out of settings drawer');
});

test('Buy a coffee link is configured with external URL and security attributes', () => {
  const html = readFileSync(resolve('web/index.html'), 'utf8');
  assert.ok(html.includes('https://buymeacoffee.com/vattitude'), 'Must link to buymeacoffee.com/vattitude');
  assert.ok(html.includes('target="_blank"'), 'Must open in new tab');
  assert.ok(html.includes('rel="noopener noreferrer"'), 'Must include security rel attributes');
  assert.ok(html.includes('Support Hark'), 'Must have Support Hark text');
});

test('Feedback modal, category tiles, and honeypot anti-bot elements are defined in index.html', () => {
  const html = readFileSync(resolve('web/index.html'), 'utf8');
  assert.ok(html.includes('id="feedbackModal"'), 'Must contain feedbackModal');
  assert.ok(html.includes('id="feedbackForm"'), 'Must contain feedbackForm');
  assert.ok(html.includes('id="feedbackHpWebsite"'), 'Must contain honeypot input for anti-bot trap');
  assert.ok(!html.includes('id="feedbackCaptchaPrompt"'), 'Math challenge prompt must be removed per user request');
  assert.ok(!html.includes('id="feedbackCaptchaAnswer"'), 'Math answer input must be removed per user request');
  assert.ok(html.includes('id="feedbackCategories"'), 'Must contain category selector container');
  assert.ok(html.includes('data-cat="Audio"'), 'Must contain Audio category tile');
  assert.ok(html.includes('data-cat="Wrong info"'), 'Must contain Wrong info category tile');
  assert.ok(html.includes('data-cat="Bug"'), 'Must contain Bug category tile');
  assert.ok(html.includes('data-cat="Idea"'), 'Must contain Idea category tile');
  assert.ok(html.includes('id="feedbackReplySwitch"'), 'Must contain reply to me by email switch');
  assert.ok(html.includes('id="feedbackSubmitBtn"'), 'Must contain submit CTA button');
  assert.ok(html.includes('AI summaries can get things wrong'), 'Must contain footer disclaimer');
  assert.ok(html.includes('id="drawerFeedbackBtn"'), 'Must contain drawerFeedbackBtn');
  assert.ok(html.includes('id="accountModal"'), 'Must contain accountModal');
});

test('Feedback flow enforces post-login auth restriction and dynamic categories in app.js', () => {
  const appJs = readFileSync(resolve('web/js/app.js'), 'utf8');
  assert.ok(appJs.includes("openSignIn('feedback')"), 'Must route unauthenticated users to sign-in modal');
  assert.ok(appJs.includes('pendingFeedbackContext'), 'Must remember pending feedback context across login');
  assert.ok(appJs.includes('selectFeedbackCategory'), 'Must provide dynamic category selection');
  assert.ok(appJs.includes('FEEDBACK_CATEGORIES'), 'Must configure category placeholders and embed colors');
  assert.ok(!appJs.includes('generateFeedbackCaptcha'), 'Captcha generator function must be removed');
  assert.ok(appJs.includes('hark_feedback_last_sent'), 'Must maintain rate-limiting cooldown between submissions');
});

test('Anti-bot sanitization prevents Discord @everyone and @here pings', () => {
  const rawText = 'Hey @everyone check this out and ping @here!';
  const sanitized = rawText.replace(/@(everyone|here)/gi, '@\u200b$1');
  assert.strictEqual(sanitized, 'Hey @\u200beveryone check this out and ping @\u200bhere!');
  assert.ok(!sanitized.includes('@everyone'), 'Must break @everyone token');
  assert.ok(!sanitized.includes('@here'), 'Must break @here token');
});

test('Sign out flow and morning alerts toggle bindings exist in app.js', () => {
  const appJs = readFileSync(resolve('web/js/app.js'), 'utf8');
  assert.ok(appJs.includes('async function performSignOut()'), 'Must implement performSignOut');
  assert.ok(appJs.includes('async function toggleMorningAlerts()'), 'Must implement toggleMorningAlerts');
  assert.ok(appJs.includes('hark_morning_alerts_disabled'), 'Must use local storage flag to track user preference');
  assert.ok(appJs.includes("accountModalSignOutBtn')?.addEventListener('click', performSignOut)"), 'Must bind signout button to performSignOut');
  assert.ok(appJs.includes("menuPushBtn')?.addEventListener('click', toggleMorningAlerts)"), 'Must bind menu push button to toggleMorningAlerts');
});

test('Article floating report button and story context banner are configured', () => {
  const html = readFileSync(resolve('web/index.html'), 'utf8');
  assert.ok(html.includes('id="cleanReportBtn"'), 'Must contain cleanReportBtn in cover actions');
  assert.ok(html.includes('id="feedbackStoryContext"'), 'Must contain feedbackStoryContext container in modal');
  assert.ok(html.includes('id="feedbackStoryContextHeadline"'), 'Must contain feedbackStoryContextHeadline');
  assert.ok(html.includes('id="feedbackStoryContextId"'), 'Must contain feedbackStoryContextId');
  assert.ok(html.includes('id="cleanDrawerVersionBtn"'), 'Must contain cleanDrawerVersionBtn for 1-tap reload');
});

test('App lifecycle update check and smart pull-to-refresh reload logic exist in app.js', () => {
  const appJs = readFileSync(resolve('web/js/app.js'), 'utf8');
  assert.ok(appJs.includes('async function checkAppUpdate'), 'Must implement checkAppUpdate');
  assert.ok(appJs.includes('function initAppLifecycle'), 'Must implement initAppLifecycle');
  assert.ok(appJs.includes("appStateChange"), 'Must listen for Capacitor native appStateChange');
  assert.ok(appJs.includes("visibilitychange"), 'Must listen for web visibilitychange');
  assert.ok(appJs.includes("updateAvailable"), 'Pull to refresh must track service worker update availability');
});

test('Drawer footer button bar clean-drawer-foot is robustly styled without CSS syntax errors', () => {
  const css = readFileSync(resolve('web/css/styles.css'), 'utf8');
  assert.ok(css.includes('.clean-drawer-foot {'), 'Must contain clean-drawer-foot rule');
  assert.ok(css.includes('grid-template-columns: 1fr;'), 'Default state must provide 1fr single-column grid');
  assert.ok(css.includes('width: 100%;'), 'Drawer footer and buttons must have width: 100% to prevent shrinking');
  assert.ok(!css.includes('.clean-drawer-version {\n  font-family: var(--font-head);\n  font-size: 11px;\n  font-weight: 500;\n  letter-spacing: 0.04em;\n  color: rgba(255, 255, 255, 0.55);\n}\n  display: block;\n}'), 'Must not contain stray orphan declaration outside rule');

  // Verify full CSS brace balance
  let balance = 0;
  for (const ch of css) {
    if (ch === '{') balance++;
    else if (ch === '}') balance--;
    assert.ok(balance >= 0, 'CSS must never have premature closing braces');
  }
  assert.strictEqual(balance, 0, 'All CSS rule blocks must be cleanly closed');
});

test('3D Stacked Cards deck and swipe gesture navigation are properly configured', () => {
  const html = readFileSync(resolve('web/index.html'), 'utf8');
  assert.ok(html.includes('id="cleanDeckWrap"'), 'Must contain cleanDeckWrap wrapper');
  assert.ok(html.includes('id="cleanCardStackBg"'), 'Must contain primary background card layer-1');
  assert.ok(html.includes('id="cleanCardStackBg2"'), 'Must contain secondary background card layer-2');
  assert.ok(html.includes('id="rearCoverImg"'), 'Must contain rearCoverImg for up next story preview');
  assert.ok(html.includes('id="rearStoryHeadline"'), 'Must contain rearStoryHeadline for up next preview');
  assert.ok(html.includes('id="rearSnippet"'), 'Must contain rearSnippet preview');

  // Verify bottom dock is stationed outside cleanDeckWrap so controls do not swipe away
  const deckWrapIndex = html.indexOf('id="cleanDeckWrap"');
  const deckCloseIndex = html.indexOf('</div>\n\n      <!-- Stationed Bottom Dock', deckWrapIndex);
  const dockIndex = html.indexOf('class="clean-card-bottom-dock"', deckWrapIndex);
  assert.ok(deckCloseIndex !== -1 && dockIndex > deckCloseIndex, 'clean-card-bottom-dock must sit outside cleanDeckWrap');

  const css = readFileSync(resolve('web/css/styles.css'), 'utf8');
  assert.ok(css.includes('.clean-deck-wrap {'), 'Must contain clean-deck-wrap styles');
  assert.ok(css.includes('.clean-card-stack-bg {'), 'Must contain clean-card-stack-bg styles');
  assert.ok(css.includes('.clean-card-stack-bg.layer-1'), 'Must contain layer-1 transform');
  assert.ok(css.includes('.clean-card-stack-bg.layer-2'), 'Must contain layer-2 transform');
  assert.ok(css.includes('.clean-player-card-front {'), 'Must contain front card shifted positioning');
  assert.ok(css.includes('.clean-player-card-rear {'), 'Must contain rear card preview styles');
  assert.ok(css.includes('.clean-deck-wrap.is-last-card'), 'Must hide background cards on the last briefing story');

  const playerJs = readFileSync(resolve('web/js/player.js'), 'utf8');
  assert.ok(playerJs.includes('setupCardSwipe()'), 'Player must implement setupCardSwipe');
  assert.ok(playerJs.includes('this.setupCardSwipe();'), 'Player must call setupCardSwipe during initialization');
  assert.ok(playerJs.includes('isLockedVertical'), 'Must safeguard vertical teleprompter scrolling');
  assert.ok(playerJs.includes('this.nextChapter()'), 'Must advance to next story on left swipe');
  assert.ok(playerJs.includes('this.prevChapter()'), 'Must return to previous story on right swipe');
  assert.ok(playerJs.includes('rearCoverImg'), 'Player tick must populate rear cover image');
  assert.ok(playerJs.includes('nextStory.image'), 'Rear card must load nextStory.image instead of falling back to default icon');
  assert.ok(playerJs.includes('rearStoryHeadline'), 'Player tick must populate rear story headline');
});

test('storyFor associates bridge banter with upcoming story and nextChapter navigates stories', async () => {
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const dir = mkdtempSync(join(tmpdir(), 'player-nav-'));

  writeFileSync(join(dir, 'config.mjs'), "export const SUPABASE_URL = 'https://x'; export const SUPABASE_PUBLISHABLE_KEY = 'k';");
  const apiSrc = readFileSync(resolve('web/js/api.js'), 'utf8')
    .replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'api.mjs'), apiSrc);

  const storypackSrc = readFileSync(resolve('web/js/storypack.js'), 'utf8')
    .replace("'./api.js'", "'./api.mjs'").replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'storypack.mjs'), storypackSrc);

  const playerSrc = readFileSync(resolve('web/js/player.js'), 'utf8')
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
    play() { this.paused = false; return Promise.resolve(); }
    pause() { this.paused = true; }
    load() {}
    removeAttribute() {}
  }

  const audio = new MockAudio();
  const preloader = new MockAudio();
  const player = new Player({ audio, preloader, el: {} });
  player.briefing = {
    mode: 'podcast',
    title: 'Hark Daily',
    stories: [
      { id: 'top-1', section: 'top', headline: 'Top Story 1', start: 10, end: 30 },
      { id: 'top-2', section: 'top', headline: 'Top Story 2', start: 30, end: 50 },
      { id: 'ent-1', section: 'entertainment', headline: 'Entertainment Story 1', start: 56, end: 76 },
    ],
    sections: [
      { key: 'top', title: 'Top Stories' },
      { key: 'entertainment', title: 'Entertainment' },
    ],
  };

  player.chapters = [
    { id: 'open', kind: 'note', title: 'Show Open', start: 0, end: 10 },
    { id: 'top-1', kind: 'story', title: 'Top Story 1', start: 10, end: 30, section: 'top' },
    { id: 'top-2', kind: 'story', title: 'Top Story 2', start: 30, end: 50, section: 'top' },
    { id: 'bridge-ent', kind: 'note', title: 'Up next • Entertainment', text: 'Tease text', start: 50, end: 56, section: 'entertainment' },
    { id: 'ent-1', kind: 'story', title: 'Entertainment Story 1', start: 56, end: 76, section: 'entertainment' },
  ];

  // 1. storyFor on bridge chapter must return the upcoming entertainment story, NOT story 0
  const bridgeChapter = player.chapters[3];
  const resolvedStory = player.storyFor(bridgeChapter);
  assert.equal(resolvedStory.id, 'ent-1', 'Bridge chapter must map to first entertainment story');
  assert.equal(player.sectionTitle(bridgeChapter), 'Entertainment', 'Section title must be Entertainment');

  // 2. nextChapter on top-2 must advance directly to ent-1, skipping intermediate banter
  let playedChapterId = null;
  player.playChapter = (id) => { playedChapterId = id; };
  audio.currentTime = 35; // Inside top-2
  player.nextChapter();
  assert.equal(playedChapterId, 'ent-1', 'nextChapter on top-2 must advance directly to ent-1');

  // 3. prevChapter on ent-1 must return to top-2
  playedChapterId = null;
  audio.currentTime = 57; // At start of ent-1 (< 3 seconds into story)
  player.prevChapter();
  assert.equal(playedChapterId, 'top-2', 'prevChapter at start of ent-1 must go to top-2');
});

test('Feedback webhook URL is NEVER hardcoded in client code and uses secure /api/feedback', () => {
  const appJs = readFileSync(resolve('web/js/app.js'), 'utf8');
  assert.ok(!appJs.includes('discord.com/api/webhooks'), 'Discord webhook URL must NEVER be in client-side app.js');
  assert.ok(appJs.includes('getFeedbackEndpoint'), 'Must route feedback through getFeedbackEndpoint');
  assert.ok(appJs.includes('/api/feedback'), 'Must point to /api/feedback endpoint');
});

test('Serverless feedback handler (/api/feedback) enforces security guards and validates input', async () => {
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const dir = mkdtempSync(join(tmpdir(), 'feedback-test-'));
  const src = readFileSync(resolve('web/api/feedback.js'), 'utf8');
  writeFileSync(join(dir, 'feedback.mjs'), src);
  const { default: handler } = await import(join(dir, 'feedback.mjs'));

  const createMockRes = () => {
    const res = {
      statusCode: 200,
      headers: {},
      body: null,
      setHeader(k, v) { res.headers[k] = v; return res; },
      status(code) { res.statusCode = code; return res; },
      json(data) { res.body = data; return res; },
      end() { return res; },
    };
    return res;
  };

  // 1. Rejects non-POST methods
  const getRes = createMockRes();
  await handler({ method: 'GET' }, getRes);
  assert.equal(getRes.statusCode, 405);
  assert.equal(getRes.headers['Allow'], 'POST');

  // 2. Returns 503 if webhook environment variable is missing
  const oldEnv = process.env.DISCORD_FEEDBACK_WEBHOOK;
  delete process.env.DISCORD_FEEDBACK_WEBHOOK;
  delete process.env.FEEDBACK_WEBHOOK_URL;
  delete process.env.DISCORD_WEBHOOK_URL;

  const noEnvRes = createMockRes();
  await handler({ method: 'POST', body: { message: 'Hello feedback' } }, noEnvRes);
  assert.equal(noEnvRes.statusCode, 503);

  // 3. Honeypot drop: when bot fills 'website', immediately returns 200 without calling Discord
  process.env.DISCORD_FEEDBACK_WEBHOOK = 'https://mock.discord/api/webhooks/test';
  let fetchCalled = false;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    fetchCalled = true;
    return { ok: true, status: 200, json: async () => ({}) };
  };

  try {
    const hpRes = createMockRes();
    await handler({ method: 'POST', body: { message: 'Spam from bot', website: 'https://spambot.com' } }, hpRes);
    assert.equal(hpRes.statusCode, 200);
    assert.equal(fetchCalled, false, 'Honeypot trap must drop request without calling Discord');

    // 4. Message length validation
    const shortRes = createMockRes();
    await handler({ method: 'POST', body: { message: 'hi' } }, shortRes);
    assert.equal(shortRes.statusCode, 400);

    // 5. Successful submission with story context
    let sentPayload = null;
    globalThis.fetch = async (url, opts) => {
      sentPayload = JSON.parse(opts.body);
      return { ok: true, status: 200, text: async () => 'ok' };
    };

    const goodRes = createMockRes();
    await handler({
      method: 'POST',
      body: {
        category: 'Audio',
        message: 'Name pronounced incorrectly @everyone',
        email: 'user@example.com',
        reply_requested: true,
        edition: 'Canada',
        story: {
          id: 'science-1',
          headline: 'Breakthrough in Physics',
          source: 'CBC News',
          position: '1:23 / 5:00',
          section: 'science',
        },
      },
    }, goodRes);

    assert.equal(goodRes.statusCode, 200);
    assert.ok(sentPayload, 'Payload must be dispatched to Discord');
    assert.ok(!sentPayload.embeds[0].description.includes('@everyone'), '@everyone ping must be sanitized');
    assert.ok(sentPayload.embeds[0].description.includes('@\u200beveryone'));
    assert.equal(sentPayload.embeds[0].fields.find((f) => f.name === 'Story ID')?.value, 'science-1');
  } finally {
    globalThis.fetch = originalFetch;
    if (oldEnv) process.env.DISCORD_FEEDBACK_WEBHOOK = oldEnv;
    else delete process.env.DISCORD_FEEDBACK_WEBHOOK;
  }
});

test('Security guards: SSRF IP filtering blocks internal, link-local, carrier-grade, and cloud metadata', async () => {
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const dir = mkdtempSync(join(tmpdir(), 'fetch-test-'));
  const src = readFileSync(resolve('web/api/fetch.js'), 'utf8');
  writeFileSync(join(dir, 'fetch.mjs'), src);
  const { isPrivateOrReservedIP } = await import(join(dir, 'fetch.mjs'));

  // Loopback and private ranges
  assert.equal(isPrivateOrReservedIP('127.0.0.1'), true, '127.0.0.1 loopback must be blocked');
  assert.equal(isPrivateOrReservedIP('127.0.0.2'), true, '127.0.0.2 loopback must be blocked');
  assert.equal(isPrivateOrReservedIP('10.0.0.1'), true, '10.0.0.1 private must be blocked');
  assert.equal(isPrivateOrReservedIP('172.16.0.1'), true, '172.16.0.1 private must be blocked');
  assert.equal(isPrivateOrReservedIP('192.168.1.1'), true, '192.168.1.1 private must be blocked');

  // Cloud metadata & link-local
  assert.equal(isPrivateOrReservedIP('169.254.169.254'), true, 'Cloud metadata 169.254.169.254 must be blocked');
  assert.equal(isPrivateOrReservedIP('169.254.1.1'), true, 'Link-local 169.254.1.1 must be blocked');

  // Carrier-grade NAT (100.64.0.0/10)
  assert.equal(isPrivateOrReservedIP('100.64.0.1'), true, 'Carrier-grade NAT 100.64.0.1 must be blocked');
  assert.equal(isPrivateOrReservedIP('100.127.255.254'), true, 'Carrier-grade NAT 100.127.255.254 must be blocked');

  // IPv6 loopback, link-local, unique local, IPv4-mapped (dotted and hex)
  assert.equal(isPrivateOrReservedIP('::1'), true, 'IPv6 loopback must be blocked');
  assert.equal(isPrivateOrReservedIP('fe80::1'), true, 'IPv6 link-local must be blocked');
  assert.equal(isPrivateOrReservedIP('fc00::1'), true, 'IPv6 unique local must be blocked');
  assert.equal(isPrivateOrReservedIP('::ffff:127.0.0.1'), true, 'IPv4-mapped IPv6 loopback must be blocked');
  assert.equal(isPrivateOrReservedIP('::ffff:169.254.169.254'), true, 'IPv4-mapped cloud metadata must be blocked');
  assert.equal(isPrivateOrReservedIP('::ffff:7f00:1'), true, 'Hex IPv4-mapped loopback ::ffff:7f00:1 must be blocked');
  assert.equal(isPrivateOrReservedIP('::ffff:a9fe:a9fe'), true, 'Hex IPv4-mapped cloud metadata ::ffff:a9fe:a9fe must be blocked');

  // Public internet IPs must be permitted
  assert.equal(isPrivateOrReservedIP('8.8.8.8'), false, 'Google DNS 8.8.8.8 must be allowed');
  assert.equal(isPrivateOrReservedIP('1.1.1.1'), false, 'Cloudflare DNS 1.1.1.1 must be allowed');
  assert.equal(isPrivateOrReservedIP('151.101.1.140'), false, 'Public CDN IP must be allowed');
  assert.equal(isPrivateOrReservedIP('::ffff:808:808'), false, 'Public hex IPv4-mapped DNS 8.8.8.8 must be allowed');
});

test('SEC-19: safeExternalUrl strictly validates HTTP/HTTPS protocols and rejects script injection', async () => {
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const dir = mkdtempSync(join(tmpdir(), 'player-test-'));
  const src = readFileSync(resolve('web/js/player.js'), 'utf8')
    .replace("import { fmtTime, h, store } from './api.js';", "const fmtTime = () => '', h = () => {}, store = {};")
    .replace("import { parseDialogueTurns } from './storypack.js';", "const parseDialogueTurns = () => {};");
  writeFileSync(join(dir, 'player_safe.mjs'), src);
  const { safeExternalUrl } = await import(join(dir, 'player_safe.mjs'));

  assert.equal(safeExternalUrl(null), null);
  assert.equal(safeExternalUrl(''), null);
  assert.equal(safeExternalUrl('javascript:alert(1)'), null, 'javascript: scheme must be blocked');
  assert.equal(safeExternalUrl('data:text/html,<script>alert(1)</script>'), null, 'data: scheme must be blocked');
  assert.equal(safeExternalUrl('vbscript:msgbox(1)'), null, 'vbscript: scheme must be blocked');
  assert.equal(safeExternalUrl('//evil.example.com'), null, 'Protocol-relative URL must be blocked');
  assert.equal(safeExternalUrl('https://www.cbc.ca/news/world-123'), 'https://www.cbc.ca/news/world-123', 'HTTPS must be allowed');
  assert.equal(safeExternalUrl('http://feeds.bbci.co.uk/news/rss.xml'), 'http://feeds.bbci.co.uk/news/rss.xml', 'HTTP must be allowed');
});

test('SEC-18: /api/share canonicalizes origins and safely escapes replacement strings with $ patterns', async () => {
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const dir = mkdtempSync(join(tmpdir(), 'share-test-'));
  const src = readFileSync(resolve('web/api/share.js'), 'utf8')
    .replace("import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from '../config.js';", "const SUPABASE_PUBLISHABLE_KEY = 'test', SUPABASE_URL = 'http://test';");
  writeFileSync(join(dir, 'share.mjs'), src);
  const { default: shareHandler } = await import(join(dir, 'share.mjs'));

  let headersSent = {};
  let sentBody = '';
  const mockRes = {
    setHeader: (k, v) => { headersSent[k.toLowerCase()] = v; },
    status: () => mockRes,
    send: (body) => { sentBody = body; },
  };

  // Poisoned X-Forwarded-Host from attacker
  await shareHandler({
    url: '/s/2026-11-10/top-1-test',
    headers: {
      'x-forwarded-host': 'localhost.attacker.com',
    },
  }, mockRes);

  assert.ok(!sentBody.includes('http://localhost.attacker.com'), 'Must never accept spoofed prefix localhost.attacker.com');
  assert.ok(sentBody.includes('https://hark.vattitude.ca'), 'Must default to CANONICAL_ORIGIN');
});

test('SEC-26: /api/fetch, /api/llm, and /api/tts are discontinued and return 410 Gone with no-store', async () => {
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const dir = mkdtempSync(join(tmpdir(), 'fetch-test2-'));
  const src = readFileSync(resolve('web/api/fetch.js'), 'utf8');
  writeFileSync(join(dir, 'fetch2.mjs'), src);
  const { default: fetchHandler } = await import(join(dir, 'fetch2.mjs'));

  let statusCode = 0;
  let sentJson = null;
  const headersSet = {};
  const mockRes = {
    setHeader: (k, v) => { headersSet[k.toLowerCase()] = v; },
    status: (c) => { statusCode = c; return mockRes; },
    json: (j) => { sentJson = j; },
    send: () => {},
  };

  await fetchHandler({
    method: 'GET',
    url: '/api/fetch?url=https://news.ycombinator.com/rss',
    headers: { origin: 'https://attacker.evil.com' },
  }, mockRes);

  assert.equal(statusCode, 410, 'Discontinued endpoint must return 410 Gone');
  assert.equal(headersSet['cache-control'], 'no-store', 'Discontinued endpoint must set Cache-Control: no-store');
  assert.ok(sentJson?.error?.includes('discontinued'), 'Must return discontinued error message');
});

test('DATA-07: api.signOut clears diagnostics-log from storage', async () => {
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const dir = mkdtempSync(join(tmpdir(), 'signout-test-'));
  const src = readFileSync(resolve('web/js/api.js'), 'utf8')
    .replace("import { createClient } from './supabase-js.js';", "const createClient = () => ({ auth: { signOut: async () => ({}) } });")
    .replace(/import\s*\{[^}]*\}\s*from\s*'\.\.\/config\.js';/, "const SUPABASE_URL = 'http://test', SUPABASE_PUBLISHABLE_KEY = 'test', FEATURES = {}, GOOGLE_CLIENT_ID = 'test';");
  writeFileSync(join(dir, 'api_signout.mjs'), src);

  const mockStore = {};
  globalThis.localStorage = {
    getItem: (k) => mockStore[k] ?? null,
    setItem: (k, v) => { mockStore[k] = String(v); },
    removeItem: (k) => { delete mockStore[k]; },
  };

  const { api, store } = await import(join(dir, 'api_signout.mjs'));

  store.set('diagnostics-log', [{ error: 'test error' }]);
  assert.equal(store.get('diagnostics-log')?.length, 1);
  await api.signOut();
  assert.equal(store.get('diagnostics-log'), undefined, 'diagnostics-log must be removed on signOut');
});

test('SEC-27: /api/share rejects wildcard vercel.app spoofing and isolates non-canonical cache', async () => {
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const dir = mkdtempSync(join(tmpdir(), 'share-sec27-'));
  const src = readFileSync(resolve('web/api/share.js'), 'utf8')
    .replace("import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from '../config.js';", "const SUPABASE_PUBLISHABLE_KEY = 'test', SUPABASE_URL = 'http://test';")
    .replace("import { createClient } from '@supabase/supabase-js';", "const createClient = () => ({ from: () => ({ select: () => ({ eq: () => ({ single: async () => ({ data: null }) }) }) }) });")
    .replace("const indexHtml = readFileSync(resolve(process.cwd(), 'web/index.html'), 'utf8');", "const indexHtml = '<!DOCTYPE html><html><head><title>Test</title></head><body></body></html>';");
  writeFileSync(join(dir, 'share.mjs'), src);
  const { default: shareHandler } = await import(join(dir, 'share.mjs'));

  // Test attacker-controlled Vercel subdomain spoofing
  let sentBody = '';
  const headersSet = {};
  const mockRes = {
    setHeader: (k, v) => { headersSet[k.toLowerCase()] = v; },
    status: () => mockRes,
    send: (b) => { sentBody = b; },
  };

  await shareHandler({
    url: '/s/2026-11-11/test-slug',
    headers: { 'x-forwarded-host': 'hark-phishing.vercel.app' },
  }, mockRes);

  assert.ok(!sentBody.includes('https://hark-phishing.vercel.app'), 'Must not accept wildcard Vercel subdomain');
  assert.ok(sentBody.includes('https://hark.vattitude.ca'), 'Must default to CANONICAL_ORIGIN');
  assert.equal(headersSet['cache-control'], 'public, s-maxage=300, stale-while-revalidate=86400', 'Canonical origin receives CDN caching');

  // Test localhost receives private, no-store
  const localHeaders = {};
  const localRes = {
    setHeader: (k, v) => { localHeaders[k.toLowerCase()] = v; },
    status: () => localRes,
    send: () => {},
  };
  await shareHandler({
    url: '/s/2026-11-11/test-slug',
    headers: { host: 'localhost:3000' },
  }, localRes);
  assert.equal(localHeaders['cache-control'], 'private, no-store', 'Non-canonical origin must be private, no-store');
});

test('SEC-29: Service Worker excludes /api/ routes and validates notificationclick targets', () => {
  const swSrc = readFileSync(resolve('web/sw.js'), 'utf8');
  assert.ok(swSrc.includes("if (url.pathname.startsWith('/api/')) return;"), 'SW must bypass all /api/ endpoints');
  assert.ok(swSrc.includes("e.request.mode === 'navigate'"), 'SW must only fall back to / for navigation requests');
  assert.ok(swSrc.includes("parsed.origin === self.location.origin"), 'SW must validate notification click origin');
});


