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

test('Feedback modal and anti-bot elements are defined in index.html', () => {
  const html = readFileSync(resolve('web/index.html'), 'utf8');
  assert.ok(html.includes('id="feedbackModal"'), 'Must contain feedbackModal');
  assert.ok(html.includes('id="feedbackForm"'), 'Must contain feedbackForm');
  assert.ok(html.includes('id="feedbackHpWebsite"'), 'Must contain honeypot input for anti-bot trap');
  assert.ok(html.includes('id="feedbackCaptchaPrompt"'), 'Must contain math challenge prompt');
  assert.ok(html.includes('id="feedbackCaptchaAnswer"'), 'Must contain math answer input');
  assert.ok(html.includes('id="drawerFeedbackBtn"'), 'Must contain drawerFeedbackBtn');
  assert.ok(html.includes('id="accountModal"'), 'Must contain accountModal');
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

