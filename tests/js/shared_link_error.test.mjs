import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

test('Standalone 404 page exists and has appropriate branding, copy, and link', () => {
  const p404Path = resolve('web/404.html');
  assert.ok(existsSync(p404Path), 'web/404.html must exist');

  const html = readFileSync(p404Path, 'utf8');
  assert.ok(html.includes('404'), 'Must mention 404 in page');
  assert.ok(html.includes('Story or Page Not Found'), 'Must have descriptive title');
  assert.ok(html.includes('Hark Daily stores audio briefings for a rolling window'), 'Must explain rolling archive policy');
  assert.ok(html.includes('href="/"'), 'Must contain link to homepage / briefing');
  assert.ok(html.includes("Listen to Today's Briefing"), 'Must have clear CTA button to listen to today');
  assert.ok(html.includes('Rolling Archive Active'), 'Must display rolling archive badge');
});

test('index.html contains the in-app shared story expired / not found modal', () => {
  const html = readFileSync(resolve('web/index.html'), 'utf8');
  assert.ok(html.includes('id="sharedStoryNotFoundModal"'), 'Must contain sharedStoryNotFoundModal element');
  assert.ok(html.includes('id="sharedErrorTitle"'), 'Must contain sharedErrorTitle');
  assert.ok(html.includes('id="sharedErrorDesc"'), 'Must contain sharedErrorDesc');
  assert.ok(html.includes('id="sharedErrorDateText"'), 'Must contain sharedErrorDateText');
  assert.ok(html.includes('id="sharedErrorListenTodayBtn"'), 'Must contain sharedErrorListenTodayBtn');
  assert.ok(html.includes('id="sharedErrorBrowseBtn"'), 'Must contain sharedErrorBrowseBtn');
  assert.ok(html.includes('id="sharedErrorCloseBtn"'), 'Must contain sharedErrorCloseBtn');
});

test('OpenGraph serverless share handler flags notFound / expired stories cleanly', () => {
  const shareJs = readFileSync(resolve('web/api/share.js'), 'utf8');
  assert.ok(shareJs.includes('const isNotFound = !storyRow'), 'Must check if storyRow was found');
  assert.ok(shareJs.includes('const isExpired = Boolean(date && date < nowStr)'), 'Must check if date is older than today');
  assert.ok(shareJs.includes('Story Expired (${date}) — Hark Daily'), 'Must customize title for expired story links');
  assert.ok(shareJs.includes('notFound: isNotFound'), 'Must expose notFound flag in window.__SHARED_STORY__');
  assert.ok(shareJs.includes('expired: isExpired'), 'Must expose expired flag in window.__SHARED_STORY__');
});

test('Service worker precaches 404.html in shell cache', () => {
  const swJs = readFileSync(resolve('web/sw.js'), 'utf8');
  assert.ok(swJs.includes("'/404.html'"), 'Must include 404.html in static SHELL cache');
});

test('app.js implements showSharedStoryError and binds modal buttons', () => {
  const appJs = readFileSync(resolve('web/js/app.js'), 'utf8');
  assert.ok(appJs.includes('function showSharedStoryError('), 'Must implement showSharedStoryError');
  assert.ok(appJs.includes('function closeSharedStoryError('), 'Must implement closeSharedStoryError');
  assert.ok(appJs.includes('window.showSharedStoryError = showSharedStoryError'), 'Must export showSharedStoryError to window');
  assert.ok(appJs.includes('sharedErrorListenTodayBtn'), 'Must bind listen today button');
  assert.ok(appJs.includes('sharedErrorBrowseBtn'), 'Must bind browse stories button');
  assert.ok(appJs.includes('sharedErrorCloseBtn'), 'Must bind close button');
});
