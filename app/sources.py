"""Built-in news sources and briefing sections."""
from __future__ import annotations

SECTIONS = {
    "canada": {"title": "Canada", "emoji": "🇨🇦", "lead": "First, the top stories from across Canada."},
    "tech": {"title": "AI & Tech", "emoji": "🤖", "lead": "Now, the latest in AI and technology."},
    "custom": {"title": "My Sources", "emoji": "⭐", "lead": "And finally, from the sources you follow."},
}

# Weights nudge ranking: editor-curated "top stories" feeds get a boost.
BUILTIN_SOURCES = [
    # --- Canada -----------------------------------------------------------
    {"name": "CBC News · Top Stories", "url": "https://www.cbc.ca/webfeed/rss/rss-topstories", "section": "canada", "weight": 1.3},
    {"name": "CBC News · Canada", "url": "https://www.cbc.ca/webfeed/rss/rss-canada", "section": "canada", "weight": 1.1},
    {"name": "CBC News · Toronto", "url": "https://www.cbc.ca/webfeed/rss/rss-canada-toronto", "section": "canada", "weight": 0.9},
    {"name": "Global News · Canada", "url": "https://globalnews.ca/canada/feed/", "section": "canada", "weight": 1.0},
    {"name": "The Globe and Mail · Canada", "url": "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/canada/", "section": "canada", "weight": 1.0},
    {"name": "National Post", "url": "https://nationalpost.com/feed", "section": "canada", "weight": 0.9},
    {"name": "CityNews Toronto", "url": "https://toronto.citynews.ca/feed/", "section": "canada", "weight": 0.8},
    # --- AI & Tech --------------------------------------------------------
    {"name": "TechCrunch · AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "section": "tech", "weight": 1.1},
    {"name": "The Verge · AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "section": "tech", "weight": 1.1},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/", "section": "tech", "weight": 1.0},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "section": "tech", "weight": 0.9},
    {"name": "VentureBeat · AI", "url": "https://venturebeat.com/category/ai/feed/", "section": "tech", "weight": 0.9},
    {"name": "The Decoder", "url": "https://the-decoder.com/feed/", "section": "tech", "weight": 0.9},
    {"name": "BetaKit (Canadian tech)", "url": "https://betakit.com/feed/", "section": "tech", "weight": 1.0},
    {"name": "CBC · Technology & Science", "url": "https://www.cbc.ca/webfeed/rss/rss-technology", "section": "tech", "weight": 0.8},
    {"name": "Hacker News · Best", "url": "https://hnrss.org/best", "section": "tech", "weight": 0.7},
]
