// Dynamic OpenGraph & short-link handler for shared stories (/s/:date/:slug).
// Queries Supabase for the story's headline, source, and duration, and returns
// index.html with compact OpenGraph meta tags so WhatsApp, iMessage, X, and
// LinkedIn render a small, clean preview card instead of a giant banner.
import fs from 'node:fs';
import path from 'node:path';
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from '../config.js';

const SECTION_LABELS = {
  top: 'Top stories',
  top_us: 'Top stories',
  top_in: 'Top stories',
  ai: 'AI',
  tech: 'Tech',
  tech_us: 'Tech',
  tech_in: 'Tech',
  politics: 'Politics',
  politics_us: 'Politics',
  politics_in: 'Politics',
  entertainment: 'Entertainment',
  entertainment_us: 'Entertainment',
  entertainment_in: 'Entertainment',
  science: 'Science',
  sports: 'Sports',
  sports_us: 'Sports',
  sports_in: 'Cricket & Sports',
};

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function stableHash(text) {
  let n = 0;
  for (let i = 0; i < text.length; i += 1) n = (n * 31 + text.charCodeAt(i)) >>> 0;
  return n;
}

export function storyKey(row) {
  if (!row) return '';
  if (row.key) return String(row.key).toLowerCase();
  const audio = row.audio_path || '';
  const m = audio.match(/-([0-9a-f]{8})\.mp3$/i);
  if (m) return m[1].toLowerCase();
  const seed = `${row.url || ''}|${row.title || row.headline || ''}|${row.section || ''}-${row.rank || ''}`;
  return stableHash(seed).toString(16).padStart(8, '0').slice(0, 8);
}

export function parseShareSlug(rawSlug) {
  const slug = String(rawSlug || '').trim().replace(/^\/+|\/+$/g, '');
  if (!slug) return { storyId: null, section: null, rank: null, hash: null };

  // Pure 8-character unique story key (region- and rank-independent)
  if (/^[0-9a-f]{8}$/i.test(slug)) {
    const key = slug.toLowerCase();
    return { storyId: key, section: null, rank: null, hash: key };
  }

  let base = slug;
  let hash = null;
  const hashMatch = slug.match(/^(.*)-([0-9a-f]{8})$/i);
  if (hashMatch) {
    base = hashMatch[1];
    hash = hashMatch[2].toLowerCase();
  }

  const rankMatch = base.match(/^([a-z_]+)-(\d+)$/i);
  if (rankMatch) {
    const section = rankMatch[1].toLowerCase();
    const rank = Number.parseInt(rankMatch[2], 10);
    return { storyId: `${section}-${rank}`, section, rank, hash };
  }

  return { storyId: base, section: null, rank: null, hash };
}

async function fetchStoryMeta(date, parsed) {
  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const endpoint = `${SUPABASE_URL}/rest/v1/story_audio?date=eq.${encodeURIComponent(date)}&select=date,section,rank,voice,title,url,source,duration,audio_path`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3000);
  try {
    const resp = await fetch(endpoint, {
      headers: {
        apikey: SUPABASE_PUBLISHABLE_KEY,
        Authorization: `Bearer ${SUPABASE_PUBLISHABLE_KEY}`,
        Accept: 'application/json',
      },
      signal: controller.signal,
    });
    if (!resp.ok) return null;
    const rows = await resp.json();
    if (!Array.isArray(rows) || !rows.length) return null;

    if (parsed.hash) {
      const byHash = rows.find((r) => storyKey(r) === parsed.hash);
      if (byHash) return byHash;
    }
    if (parsed.section && parsed.rank) {
      return (
        rows.find((r) => r.section === parsed.section && Number(r.rank) === parsed.rank && r.voice === 'matthew_reference+kelly_reference')
        || rows.find((r) => r.section === parsed.section && Number(r.rank) === parsed.rank)
        || null
      );
    }
    return null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

let cachedIndexHtml = null;

async function loadIndexHtml(origin) {
  if (cachedIndexHtml) return cachedIndexHtml;
  const candidates = [
    path.resolve(process.cwd(), 'index.html'),
    path.resolve(process.cwd(), 'web', 'index.html'),
  ];
  for (const file of candidates) {
    try {
      if (fs.existsSync(file)) {
        cachedIndexHtml = fs.readFileSync(file, 'utf8');
        return cachedIndexHtml;
      }
    } catch {
      // Fall through
    }
  }
  const resp = await fetch(`${origin}/index.html`);
  cachedIndexHtml = await resp.text();
  return cachedIndexHtml;
}

export default async function handler(req, res) {
  const proto = req.headers['x-forwarded-proto'] || 'https';
  const host = req.headers['x-forwarded-host'] || req.headers.host || 'hark.vattitude.ca';
  const origin = `${proto}://${host}`;

  const urlObj = new URL(req.url, origin);
  let date = urlObj.searchParams.get('date') || '';
  let slug = urlObj.searchParams.get('slug') || '';

  if (!date || !slug) {
    const pathMatch = urlObj.pathname.match(/^\/s\/(\d{4}-\d{2}-\d{2})\/([^/?#]+)/);
    if (pathMatch) {
      date = pathMatch[1];
      slug = decodeURIComponent(pathMatch[2]);
    }
  }

  const parsed = parseShareSlug(slug);
  const storyRow = await fetchStoryMeta(date, parsed);

  let html = await loadIndexHtml(origin);

  const headline = storyRow?.title || 'Shared Story — Hark Daily';
  const sourceName = storyRow?.source || SECTION_LABELS[parsed.section] || 'Hark Daily';
  const durSec = Math.max(1, Math.round(Number(storyRow?.duration) || 25));
  const description = storyRow
    ? `${sourceName} · ${durSec}s audio · Hark Daily`
    : 'Daily two-host audio news briefing with Matthew & Kelly.';
  const canonicalUrl = date && slug ? `${origin}/s/${encodeURIComponent(date)}/${encodeURIComponent(slug)}` : `${origin}/`;
  const thumbUrl = `${origin}/icons/og-thumb-dark.png`;

  const eTitle = escapeHtml(headline);
  const eDesc = escapeHtml(description);
  const eUrl = escapeHtml(canonicalUrl);
  const eThumb = escapeHtml(thumbUrl);

  html = html
    .replace(/<title>[\s\S]*?<\/title>/i, `<title>${eTitle} — Hark Daily</title>`)
    .replace(/<meta\s+name="description"\s+content="[^"]*">/i, `<meta name="description" content="${eDesc}">`)
    .replace(/<link\s+rel="canonical"\s+href="[^"]*">/i, `<link rel="canonical" href="${eUrl}">`)
    .replace(/<meta\s+property="og:url"\s+content="[^"]*">/i, `<meta property="og:url" content="${eUrl}">`)
    .replace(/<meta\s+property="og:title"\s+content="[^"]*">/i, `<meta property="og:title" content="${eTitle}">`)
    .replace(/<meta\s+property="og:description"\s+content="[^"]*">/i, `<meta property="og:description" content="${eDesc}">`)
    .replace(/<meta\s+property="og:image"\s+content="[^"]*">/i, `<meta property="og:image" content="${eThumb}">`)
    .replace(/<meta\s+property="og:image:secure_url"\s+content="[^"]*">/i, `<meta property="og:image:secure_url" content="${eThumb}">`)
    .replace(/<meta\s+property="og:image:width"\s+content="[^"]*">/i, '<meta property="og:image:width" content="192">')
    .replace(/<meta\s+property="og:image:height"\s+content="[^"]*">/i, '<meta property="og:image:height" content="192">')
    .replace(/<meta\s+name="twitter:url"\s+content="[^"]*">/i, `<meta name="twitter:url" content="${eUrl}">`)
    .replace(/<meta\s+name="twitter:title"\s+content="[^"]*">/i, `<meta name="twitter:title" content="${eTitle}">`)
    .replace(/<meta\s+name="twitter:description"\s+content="[^"]*">/i, `<meta name="twitter:description" content="${eDesc}">`)
    .replace(/<meta\s+name="twitter:image"\s+content="[^"]*">/i, `<meta name="twitter:image" content="${eThumb}">`);

  const sharedPayload = {
    date: date || null,
    story: storyRow ? `${storyRow.section}-${storyRow.rank}` : parsed.storyId,
    hash: parsed.hash || null,
    title: storyRow?.title || null,
    audio: storyRow?.audio_path || null,
    source: storyRow?.source || null,
    dur: durSec,
  };
  const safeJson = JSON.stringify(sharedPayload).replace(/</g, '\\u003c');
  html = html.replace('</head>', `  <script>window.__SHARED_STORY__ = ${safeJson};</script>\n</head>`);

  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=86400');
  return res.status(200).send(html);
}
