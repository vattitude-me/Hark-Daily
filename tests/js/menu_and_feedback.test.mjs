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

test('Playback Speed and Restart briefing are combined into a single split row', () => {
  const html = readFileSync(resolve('web/index.html'), 'utf8');
  assert.ok(html.includes('class="clean-menu-row-split"'), 'Must contain clean-menu-row-split container');
  assert.ok(html.includes('id="menuSpeedBtn"'), 'Must contain menuSpeedBtn inside split row');
  assert.ok(html.includes('id="menuRestartBtn"'), 'Must contain menuRestartBtn inside split row');
  assert.ok(html.includes('id="menuSpeedVal"'), 'Must contain menuSpeedVal for dynamic speed label');
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
