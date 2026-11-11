// CORS proxy for RSS/Atom feeds with comprehensive SSRF protection.
// Validates resolved IP addresses against private, loopback, carrier-grade, and cloud metadata ranges.
// Enforces 2MB maximum response payload and disallows unvalidated HTTP redirects.

import dns from 'node:dns/promises';
import { isIP } from 'node:net';

const ALLOWED_ORIGINS = new Set([
  'https://hark.vattitude.ca',
  'capacitor://localhost',
  'http://localhost:3000',
  'http://localhost:5173',
  'http://127.0.0.1:3000',
  'http://127.0.0.1:5173',
]);

export function isPrivateOrReservedIP(ipStr) {
  if (!ipStr) return true;
  const cleanIp = ipStr.startsWith('::ffff:') ? ipStr.slice(7) : ipStr;

  if (isIP(cleanIp) === 4) {
    const parts = cleanIp.split('.').map(Number);
    if (parts.length !== 4 || parts.some((n) => Number.isNaN(n) || n < 0 || n > 255)) return true;

    // 0.0.0.0/8 (Broadcast/Current network)
    if (parts[0] === 0) return true;
    // 10.0.0.0/8 (Private)
    if (parts[0] === 10) return true;
    // 127.0.0.0/8 (Loopback)
    if (parts[0] === 127) return true;
    // 100.64.0.0/10 (Carrier-grade NAT)
    if (parts[0] === 100 && parts[1] >= 64 && parts[1] <= 127) return true;
    // 169.254.0.0/16 (Link-local & Cloud Metadata 169.254.169.254)
    if (parts[0] === 169 && parts[1] === 254) return true;
    // 172.16.0.0/12 (Private)
    if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return true;
    // 192.168.0.0/16 (Private)
    if (parts[0] === 192 && parts[1] === 168) return true;
    // 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 (Test-Net documentation)
    if (parts[0] === 192 && parts[1] === 0 && parts[2] === 2) return true;
    if (parts[0] === 198 && parts[1] === 51 && parts[2] === 100) return true;
    if (parts[0] === 203 && parts[1] === 0 && parts[2] === 113) return true;
    // 224.0.0.0/4 (Multicast) & 240.0.0.0/4 (Reserved)
    if (parts[0] >= 224) return true;
    return false;
  }

  if (isIP(cleanIp) === 6) {
    const lower = cleanIp.toLowerCase();
    // ::1 (Loopback)
    if (lower === '::1' || lower === '0:0:0:0:0:0:0:1') return true;
    // fe80::/10 (Link-local)
    if (lower.startsWith('fe8') || lower.startsWith('fe9') || lower.startsWith('fea') || lower.startsWith('feb')) return true;
    // fc00::/7 (Unique local address)
    if (lower.startsWith('fc') || lower.startsWith('fd')) return true;
    // :: (Unspecified)
    if (lower === '::') return true;
    return false;
  }

  return true;
}

export default async function handler(req, res) {
  // CORS check
  const reqOrigin = (req.headers.origin || '').trim();
  const isAllowedOrigin = !reqOrigin || ALLOWED_ORIGINS.has(reqOrigin) || reqOrigin.endsWith('.vercel.app');

  if (reqOrigin && isAllowedOrigin) {
    res.setHeader('Access-Control-Allow-Origin', reqOrigin);
    res.setHeader('Vary', 'Origin');
  } else if (reqOrigin) {
    return res.status(403).json({ error: 'Origin not allowed' });
  }

  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ error: 'GET only.' });
  }

  const rawUrl = new URL(req.url, 'http://localhost').searchParams.get('url');
  if (!rawUrl || !/^https?:\/\//i.test(rawUrl)) {
    return res.status(400).json({ error: 'Provide a url query parameter starting with http(s).' });
  }

  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return res.status(400).json({ error: 'Invalid URL.' });
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return res.status(400).json({ error: 'Only http and https protocols are supported.' });
  }

  // Pre-filter known dangerous hostname patterns
  const host = parsed.hostname.toLowerCase();
  if (
    host === 'localhost' ||
    host === 'metadata.google.internal' ||
    host.endsWith('.localhost') ||
    host.endsWith('.local')
  ) {
    return res.status(403).json({ error: 'Access to local or metadata host is prohibited.' });
  }

  // Resolve hostname via DNS and verify IP range
  try {
    const addresses = await dns.lookup(parsed.hostname, { all: true });
    if (!addresses || !addresses.length) {
      return res.status(400).json({ error: 'Could not resolve host.' });
    }
    for (const addr of addresses) {
      if (isPrivateOrReservedIP(addr.address)) {
        return res.status(403).json({ error: 'Host resolves to a private or reserved network address.' });
      }
    }
  } catch (err) {
    return res.status(400).json({ error: `DNS resolution failed: ${err.message}` });
  }

  try {
    const upstream = await fetch(parsed.href, {
      headers: {
        'User-Agent': 'HarkDaily/1.0 (+https://hark.vattitude.ca)',
        Accept: 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*',
      },
      redirect: 'manual', // Prevent SSRF via open HTTP redirects
    });

    if (upstream.status >= 300 && upstream.status < 400) {
      return res.status(400).json({ error: 'Upstream redirects are prohibited by security policy.' });
    }

    // Response size limit: 2MB cap
    const MAX_BYTES = 2 * 1024 * 1024;
    const arrayBuffer = await upstream.arrayBuffer();
    if (arrayBuffer.byteLength > MAX_BYTES) {
      return res.status(413).json({ error: 'Upstream response exceeds maximum allowed limit (2MB).' });
    }

    const text = Buffer.from(arrayBuffer).toString('utf-8');
    res.setHeader('Cache-Control', 'public, max-age=300');
    res.setHeader('Content-Type', upstream.headers.get('content-type') || 'application/xml');
    return res.status(upstream.status).send(text);
  } catch (err) {
    return res.status(502).json({ error: `Fetch failed: ${err.message}` });
  }
}
