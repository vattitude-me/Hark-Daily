// Public Supabase settings for the web app. Publishable keys are safe to ship:
// row-level security (supabase/schema.sql) limits every signed-in user to their own data.
// Never put the secret key here.
const PROD_SUPABASE = {
  url: 'https://oohbmeffdncyzujmeqcz.supabase.co',
  publishableKey: 'sb_publishable_HgWQGelTuCEU6ayqFdY4Cg_F_-VVEYv',
};

const PREPROD_SUPABASE = {
  url: 'https://hhcygubulddewtwkedkz.supabase.co',
  publishableKey: 'sb_publishable_8vYLo4tLmmKDbThLnLKatA_7xBhV2jC',
};

export function isPreprodHost(hostname = '') {
  const host = String(hostname || '').toLowerCase();
  return (
    host === 'localhost'
    || host === '127.0.0.1'
    || host.endsWith('.vercel.app')
    || host.startsWith('dev.')
    || host.startsWith('preprod.')
  );
}

export function resolveSupabaseConfig({
  hostname = typeof window !== 'undefined' ? window.location?.hostname : '',
  env = typeof process !== 'undefined' ? process.env : {},
} = {}) {
  const envUrl = env?.SUPABASE_URL?.trim();
  const envKey = (env?.SUPABASE_ANON_KEY || env?.SUPABASE_PUBLISHABLE_KEY)?.trim();
  if (envUrl && envKey) {
    const cleanUrl = envUrl.replace(/\/+$/, '');
    return { url: cleanUrl, publishableKey: envKey, isPreprod: cleanUrl !== PROD_SUPABASE.url };
  }
  const usePreprod = env?.VERCEL_ENV === 'preview'
    || env?.VERCEL_ENV === 'development'
    || isPreprodHost(hostname);
  const target = usePreprod ? PREPROD_SUPABASE : PROD_SUPABASE;
  return { ...target, isPreprod: usePreprod };
}

const resolvedSupabase = resolveSupabaseConfig();
export const SUPABASE_URL = resolvedSupabase.url;
export const SUPABASE_PUBLISHABLE_KEY = resolvedSupabase.publishableKey;
export const IS_PREPROD = resolvedSupabase.isPreprod;

// Front-end feature switches. Podcast mode needs BOTH this and the server flag (PODCAST_ENABLED,
// published in app_status) to be on, so either side can switch it off. Rapid Fire is hidden, not
// removed: set `rapid: true` to bring the button back.
export const FEATURES = { podcast: true, rapid: false };

// Google Identity Services (GIS) Web Client ID for branded OAuth & One Tap
export const GOOGLE_CLIENT_ID = (typeof window !== 'undefined' && (window.__GOOGLE_CLIENT_ID__ || window.GOOGLE_CLIENT_ID))
  || (typeof process !== 'undefined' && (process.env?.GOOGLE_CLIENT_ID || process.env?.VITE_GOOGLE_CLIENT_ID || process.env?.NEXT_PUBLIC_GOOGLE_CLIENT_ID))
  || '345556028045-h61lt911l04gttt66ludkvsqr90cg9b0.apps.googleusercontent.com';

// Release version displayed in drawer and settings
export const APP_VERSION = 'v1.0.25';
