// Public Supabase settings for the web app. The publishable key is safe to ship:
// row-level security (supabase/schema.sql) limits every signed-in user to their own data.
// Never put the secret key here.
export const SUPABASE_URL = 'https://oohbmeffdncyzujmeqcz.supabase.co';
export const SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_HgWQGelTuCEU6ayqFdY4Cg_F_-VVEYv';

// Front-end feature switches. Podcast mode needs BOTH this and the server flag (PODCAST_ENABLED,
// published in app_status) to be on, so either side can switch it off. Rapid Fire is hidden, not
// removed: set `rapid: true` to bring the button back.
export const FEATURES = { podcast: true, rapid: false };
