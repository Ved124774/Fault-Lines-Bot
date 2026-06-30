"""
scraper.py
----------
Fetches articles from a broad set of RSS feeds, then uses Gemini to judge
relevance rather than relying on a fixed keyword list.
"""

import requests
import feedparser
from bs4 import BeautifulSoup
import google.generativeai as genai
import os
import json

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

RSS_FEEDS = [
    "https://foreignpolicy.com/feed/",
    "https://www.economist.com/international/rss.xml",
    "https://www.economist.com/business/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    "https://www.politico.com/rss/politicopicks.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.wired.com/feed/rss",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.reuters.com/rssFeed/businessNews",
    "https://www.ft.com/rss/home",
    "https://feeds.bloomberg.com/technology/news.rss",
    "https://www.defensenews.com/arc/outboundfeeds/rss/",
    "https://breakingdefense.com/feed/",
    "https://asia.nikkei.com/rss/feed/nar",
    "https://www.scmp.com/rss/91/feed",
]


def scrape_raw_articles(max_per_feed: int = 8):
    """Pull articles from all RSS feeds."""
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            source_name = feed.feed.get("title", feed_url)
            for entry in feed.entries[:max_per_feed]:
                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", "").strip()
                link = getattr(entry, "link", "").strip()
                if title and link:
                    articles.append({
                        "title": title,
                        "summary": summary[:600],
                        "link": link,
                        "source": source_name,
                    })
        except Exception as e:
            print(f"  Feed error ({feed_url}): {e}")
    return articles


def filter_relevant_articles(articles, max_relevant: int = 20):
    """
    Send article titles and summaries to Gemini and ask it to judge
    relevance to tech geopolitics, with no fixed keyword list.
    """
    if not articles:
        return []

    seen = set()
    unique = []
    for a in articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)

    numbered = "\n".join(
        f"{i+1}. [{a['source']}] {a['title']} — {a['summary'][:200]}"
        for i, a in enumerate(unique)
    )

    prompt = f"""You are the editorial filter for Fault Lines, a newsletter about the geopolitics of business.

Decide which of these articles are genuinely relevant to that beat. Relevant topics include, but are not
limited to: semiconductors and chip manufacturing, undersea cables and satellite infrastructure, rare earths
and critical minerals, AI policy and compute infrastructure, sanctions and export controls, industrial policy,
supply chain shifts driven by geopolitics, great power competition over technology and trade, small countries
or companies with outsized leverage in global supply chains, cybersecurity as a geopolitical tool, and energy
infrastructure with geopolitical stakes. Use judgment beyond this list too, if something is clearly about how
nation-states and business power intersect, include it.

NOT relevant: pure domestic politics with no international business angle, sports, entertainment, celebrity
news, routine corporate earnings with no geopolitical dimension.

Articles:
{numbered}

Return ONLY a JSON array of the numbers of relevant articles, e.g. [1, 3, 7, 12]. No explanation, no markdown."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip().strip("```json").strip("```").strip()
        indices = json.loads(text)
        relevant = [unique[i - 1] for i in indices if 1 <= i <= len(unique)]
        return relevant[:max_relevant]
    except Exception as e:
        print(f"  Gemini filter error: {e}")
        return unique[:max_relevant]


def get_articles(max_relevant: int = 20):
    """Full pipeline: scrape, then filter for relevance."""
    print("  Scraping RSS feeds...")
    raw = scrape_raw_articles()
    print(f"  Got {len(raw)} raw articles")

    print("  Filtering for relevance with Gemini...")
    relevant = filter_relevant_articles(raw, max_relevant=max_relevant)
    print(f"  {len(relevant)} relevant articles found")

    return relevant
