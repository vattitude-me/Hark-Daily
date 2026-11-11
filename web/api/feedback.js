// Serverless proxy for user feedback submission.
// Keeps Discord webhook URL strictly private and unexposed in repository or client bundles.

export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ error: 'Method Not Allowed' });
  }

  const webhookUrl = process.env.DISCORD_FEEDBACK_WEBHOOK || process.env.FEEDBACK_WEBHOOK_URL || process.env.DISCORD_WEBHOOK_URL;
  if (!webhookUrl) {
    console.warn('[Feedback API] DISCORD_FEEDBACK_WEBHOOK is not configured in environment variables.');
    return res.status(503).json({ error: 'Feedback service temporarily unconfigured' });
  }

  let body = req.body;
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body);
    } catch {
      return res.status(400).json({ error: 'Invalid JSON body' });
    }
  }
  body = body || {};

  // 1. Server-side honeypot drop (bots filling website input)
  if (body.website) {
    return res.status(200).json({ ok: true, dropped: true });
  }

  // 2. Validate message length
  const rawMessage = String(body.message || '').trim();
  if (rawMessage.length < 5) {
    return res.status(400).json({ error: 'Message must be at least 5 characters' });
  }
  if (rawMessage.length > 2000) {
    return res.status(400).json({ error: 'Message exceeds 2000 characters' });
  }

  // 3. Sanitize @everyone and @here pings
  const safeMessage = rawMessage.replace(/@(everyone|here)/gi, '@\u200b$1');

  // 4. Extract metadata
  const category = String(body.category || 'Idea').slice(0, 50);
  const email = String(body.email || 'Authenticated User').slice(0, 100);
  const replyRequested = body.reply_requested ? `Yes (${email})` : 'No (reply not requested)';
  const edition = String(body.edition || 'Canada').slice(0, 50);
  const appVersion = String(body.app_version || 'Hark Daily').slice(0, 50);

  const CATEGORY_COLORS = {
    Audio: 0xF59E0B,
    'Wrong info': 0xEF4444,
    Bug: 0xEC4899,
    Idea: 0x3B82F6,
  };
  const embedColor = CATEGORY_COLORS[category] || 0xF59E0B;

  const embedFields = [
    { name: 'Category', value: category, inline: true },
    { name: 'Reply Requested', value: replyRequested, inline: true },
    { name: 'Edition', value: edition, inline: true },
  ];

  if (body.story && typeof body.story === 'object') {
    if (body.story.id) {
      embedFields.push({ name: 'Story ID', value: String(body.story.id).slice(0, 80), inline: true });
    }
    if (body.story.headline) {
      embedFields.push({ name: 'Article Headline', value: String(body.story.headline).slice(0, 250), inline: false });
    }
    if (body.story.source) {
      embedFields.push({ name: 'Source', value: String(body.story.source).slice(0, 80), inline: true });
    }
    if (body.story.position) {
      embedFields.push({ name: 'Audio Timestamp', value: String(body.story.position).slice(0, 50), inline: true });
    }
    if (body.story.section) {
      embedFields.push({ name: 'Section', value: String(body.story.section).slice(0, 50), inline: true });
    }
  }

  embedFields.push(
    { name: 'Client', value: appVersion, inline: true },
    { name: 'User Profile', value: email, inline: true }
  );

  const discordPayload = {
    username: 'Hark Feedback Bot',
    avatar_url: 'https://hark.vattitude.ca/icons/logo-transparent.png',
    embeds: [
      {
        title: `[${category}] Feedback from ${email}${body.story ? ' (Story Attached)' : ''}`,
        description: safeMessage,
        color: embedColor,
        fields: embedFields,
        footer: { text: body.story?.id ? `Story ID: ${body.story.id} · Hark Feedback Shield` : 'Hark Feedback Shield' },
        timestamp: new Date().toISOString(),
      },
    ],
  };

  try {
    const discordRes = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(discordPayload),
    });

    if (!discordRes.ok) {
      const errText = await discordRes.text().catch(() => '');
      console.error(`[Feedback API] Discord responded with HTTP ${discordRes.status}: ${errText.slice(0, 200)}`);
      return res.status(502).json({ error: 'Failed to deliver message to Discord' });
    }

    return res.status(200).json({ ok: true });
  } catch (err) {
    console.error('[Feedback API] Error forwarding to Discord:', err);
    return res.status(500).json({ error: 'Internal server error' });
  }
}
