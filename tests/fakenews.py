"""Offline sample feeds and article pages for tests and local demos.

All stories are fictional sample content.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape

import httpx

STORIES = {
    "canada": [
        ("Bank of Canada holds key interest rate steady at 2.5 per cent",
         "The Bank of Canada kept its benchmark rate unchanged on Wednesday, pointing to cooling inflation and a softer job market. "
         "Governor officials said the economy is adjusting to trade uncertainty and that future moves will depend on incoming data. "
         "Economists had widely expected the pause after two cuts earlier this year. "
         "Mortgage holders on variable rates will see no immediate change to their payments. "
         "The central bank said core inflation measures have eased to around 2.6 per cent. "
         "Its next rate announcement is scheduled for late October."),
        ("Toronto transit expansion: Ontario Line reaches tunnelling milestone",
         "Crews working on Toronto's Ontario Line finished boring the first stretch of tunnel under the downtown core this week. "
         "Metrolinx said the milestone keeps the project on its revised schedule, with service expected early next decade. "
         "The 15.6-kilometre subway line will connect Exhibition Place to the Ontario Science Centre. "
         "City councillors welcomed the news but pressed the province for firmer cost estimates. "
         "Residents along the route have complained about construction noise and road closures."),
        ("Wildfire season ends with fewer hectares burned than last year, officials say",
         "Canada's wildfire season is winding down with far less land burned than the record-setting seasons of recent years. "
         "The Canadian Interagency Forest Fire Centre said cooler, wetter weather in August helped crews contain large fires. "
         "Still, several communities in northern Manitoba and Saskatchewan were evacuated during the summer. "
         "Officials said investments in firefighting aircraft and training paid off."),
        ("Federal government unveils new housing plan aimed at first-time buyers",
         "Ottawa announced a package of measures on Tuesday meant to help first-time home buyers enter the market. "
         "The plan includes expanded tax-free savings for down payments and incentives for builders to add starter homes. "
         "Housing advocates said the measures are a step forward but fall short of what is needed in Toronto and Vancouver. "
         "The opposition called the plan too little, too late."),
        ("Blue Jays clinch playoff spot with walk-off win at Rogers Centre",
         "The Toronto Blue Jays secured a post-season berth on Monday night with a dramatic walk-off single in the tenth inning. "
         "A sellout crowd at the Rogers Centre erupted as the winning run crossed the plate. "
         "The team will learn its wild-card opponent later this week."),
    ],
    "canada2": [
        ("Bank of Canada leaves interest rate unchanged as inflation cools",
         "The Bank of Canada held its policy rate at 2.5 per cent, citing easing price pressures. "
         "Analysts said a cut remains possible before the end of the year if unemployment keeps rising."),
        ("Canada Post and union reach tentative deal, averting strike",
         "Canada Post and the union representing its workers reached a tentative agreement early Tuesday, averting a strike. "
         "Details were not released, but the union said the deal addresses wages and pensions. "
         "Members will vote on the agreement over the next three weeks."),
    ],
    "tech": [
        ("New open-source AI model rivals top commercial systems on coding benchmarks",
         "A research lab released an open-weight AI model this week that matches leading commercial systems on several coding benchmarks. "
         "The model can run on a single high-end GPU, making it accessible to smaller companies and researchers. "
         "Experts cautioned that benchmark scores don't always reflect real-world performance. "
         "The release adds pressure on large AI companies to justify premium pricing."),
        ("Toronto AI startup raises $120M to build voice agents for hospitals",
         "A Toronto-based startup building AI voice assistants for hospital front desks has raised 120 million dollars in Series B funding. "
         "The company says its agents handle appointment booking and prescription refills in English and French. "
         "The round was led by a Silicon Valley venture firm, with participation from Canadian pension funds. "
         "The startup plans to double its engineering team in Toronto and Montreal."),
        ("Chipmakers race to build more efficient data-centre processors as AI demand soars",
         "Semiconductor companies are unveiling new processors designed to cut the energy used by AI data centres. "
         "Power consumption has become a key constraint as companies build ever-larger clusters for training models. "
         "Analysts expect spending on AI infrastructure to keep climbing through next year."),
        ("Canada's AI safety institute publishes first report on frontier model risks",
         "The Canadian AI Safety Institute released its first public report assessing risks from advanced AI systems. "
         "The report recommends stronger testing before powerful models are deployed and more transparency from developers. "
         "Researchers in Montreal and Toronto contributed to the analysis."),
        ("Best laptop deals this week: 30% off popular models",
         "Retailers are discounting several popular laptops this week."),
        ("Smartphone makers bet on on-device AI features to spark upgrades",
         "Phone makers are adding AI features that run directly on the device, such as live translation and photo editing. "
         "Companies hope the features will convince consumers to upgrade after years of slowing sales. "
         "Privacy advocates say on-device processing is a welcome shift away from the cloud."),
    ],
}

SOURCE_NAMES = {"canada": "Maple Daily", "canada2": "Northern Wire", "tech": "Circuit Report"}


def slug(title: str) -> str:
    return "-".join(title.lower().split()[:6]).replace(":", "").replace(",", "").replace("$", "")


def rss(key: str, base: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    items = []
    for i, (title, body) in enumerate(STORIES[key]):
        link = f"{base}/{key}/articles/{slug(title)}"
        pub = format_datetime(now - timedelta(hours=2 + i * 3))
        first = body.split(". ")[0] + "."
        items.append(
            f"<item><title>{escape(title)}</title><link>{link}</link><pubDate>{pub}</pubDate>"
            f"<description>{escape(first)}</description>"
            f'<media:content url="https://picsum.photos/seed/{key}{i}/800/450" medium="image"/></item>'
        )
    return (
        '<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>'
        f"<title>{SOURCE_NAMES[key]}</title><link>{base}</link>{''.join(items)}</channel></rss>"
    )


def article_html(key: str, page_slug: str) -> str | None:
    for title, body in STORIES.get(key, []):
        if slug(title) == page_slug:
            paras = "".join(f"<p>{escape(p.strip())}.</p>" for p in body.rstrip(".").split(". "))
            return (
                f"<html><head><title>{escape(title)}</title><meta property='og:type' content='article'></head>"
                f"<body><nav><a href='/'>Home</a></nav><article><h1>{escape(title)}</h1>{paras}"
                f"<p>{escape(body)}</p></article></body></html>"
            )
    return None


def home_html(base: str) -> str:
    return (
        "<html><head><title>Maple Daily</title>"
        f"<link rel='alternate' type='application/rss+xml' href='{base}/canada/feed.xml'></head>"
        "<body><h1>Maple Daily</h1></body></html>"
    )


def handler(base: str):
    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        parts = [p for p in path.split("/") if p]
        if len(parts) == 2 and parts[1] == "feed.xml" and parts[0] in STORIES:
            return httpx.Response(200, text=rss(parts[0], base), headers={"content-type": "application/rss+xml"})
        if len(parts) == 3 and parts[1] == "articles":
            page = article_html(parts[0], parts[2])
            if page:
                return httpx.Response(200, text=page, headers={"content-type": "text/html"})
        if path in ("", "/"):
            return httpx.Response(200, text=home_html(base), headers={"content-type": "text/html"})
        return httpx.Response(404, text="not found")

    return respond
