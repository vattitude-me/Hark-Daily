import { isIP } from 'node:net';

// IP address range validator for network boundaries and SSRF defenses (SEC-17 / SEC-26)
export function isPrivateOrReservedIP(ipStr) {
  let cleanIp = (ipStr || '').trim();
  if (cleanIp.startsWith('[') && cleanIp.endsWith(']')) {
    cleanIp = cleanIp.slice(1, -1);
  }
  const type = isIP(cleanIp);
  if (!type) return true;

  if (type === 4) {
    const parts = cleanIp.split('.').map(Number);
    if (parts.length !== 4) return true;
    const [p0, p1, p2, p3] = parts;
    if (p0 === 0 || p0 === 127) return true;
    if (p0 === 10) return true;
    if (p0 === 172 && p1 >= 16 && p1 <= 31) return true;
    if (p0 === 192 && p1 === 168) return true;
    if (p0 === 169 && p1 === 254) return true;
    if (p0 === 100 && p1 >= 64 && p1 <= 127) return true;
    if (p0 >= 224) return true;
    return false;
  }

  const lower = cleanIp.toLowerCase();
  if (lower === '::' || lower === '::1') return true;
  if (lower.startsWith('::ffff:')) {
    const mapped = lower.slice(7);
    if (mapped.includes('.')) {
      return isPrivateOrReservedIP(mapped);
    }
    const hexParts = mapped.split(':');
    if (hexParts.length === 2) {
      const p1 = parseInt(hexParts[0], 16);
      const p2 = parseInt(hexParts[1], 16);
      if (!isNaN(p1) && !isNaN(p2)) {
        const ipv4 = `${(p1 >> 8) & 0xff}.${p1 & 0xff}.${(p2 >> 8) & 0xff}.${p2 & 0xff}`;
        return isPrivateOrReservedIP(ipv4);
      }
    }
    return true;
  }
  if (lower.startsWith('fe80:') || lower.startsWith('fe9') || lower.startsWith('fea') || lower.startsWith('feb')) return true;
  if (lower.startsWith('fc') || lower.startsWith('fd')) return true;
  return false;
}

// Legacy client RSS/Atom CORS proxy — discontinued (SEC-26).
// News feed aggregation runs exclusively through backend topics collector (app/topics.py).
export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  return res.status(410).json({ error: 'Endpoint discontinued' });
}
