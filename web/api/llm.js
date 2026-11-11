// Legacy BYOK LLM proxy endpoint — discontinued (SEC-26).
// Client-side BYOK builder has been removed; server audio runs through backend worker pipeline.
export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  return res.status(410).json({ error: 'Endpoint discontinued' });
}
