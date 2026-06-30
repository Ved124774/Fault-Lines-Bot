"""
bluesky_bot.py
--------------
Daily Bluesky activity for Fault Lines:
  1. Scrapes news headlines
  2. Makes exactly ONE Gemini call to write an original post AND a reply
  3. Posts the original content
  4. Replies to a genuinely substantive post found in the wild
  5. Follows a few relevant accounts
"""

import os
import json
import time
import feedparser
import google.generativeai as genai

from bluesky_client import BlueskyClient

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash-lite")

VOICE_GUIDE = """
VOICE RULES:
- Sound like a sharp, curious person who actually finds this stuff fascinating, not a brand account.
- Plain language, no jargon without explanation.
- A little dry humour is good. Don't force it.
- NEVER use em dashes (-). Use commas or periods instead.
- Vary sentence rhythm, avoid sounding uniform or robotic.
- No hashtags. No "thread below". No corporate phrasing.
- Be specific. Reference an actual fact, company, or country, not vague generalities.
"""

RSS_FEEDS = [
    "https://foreignpolicy.com/feed/",
    "https://www.economist.com/international/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://techcrunch.com/feed/",
    "https://www.reuters.com/rssFeed/businessNews",
    "https://www.ft.com/rss/home",
]


def call_gemini_with_retry(prompt, max_retries=3, wait_time=30):
    """Call Gemini, retry a sensible number of times on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                print(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise
    raise Exception("Max retries exceeded for Gemini call")


def scrape_headlines(max_per_feed=4):
    """Pull plain headlines and short summaries from RSS feeds."""
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:max_per_feed]:
                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", "").strip()
                if title:
                    articles.append({"title": title, "summary": summary[:150]})
        except Exception as e:
            print(f"Feed error ({feed_url}): {e}")

    seen = set()
    unique = []
    for a in articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)
    return unique


def pick_post_to_reply_to(posts):
    """Pick the most substantive post by length, no Gemini call needed."""
    if not posts:
        return None
    candidates = [p for p in posts if len(p.get("record", {}).get("text", "")) > 100]
    if not candidates:
        candidates = posts
    return max(candidates, key=lambda p: len(p.get("record", {}).get("text", "")))


def generate_post_and_reply(articles, reply_target_text, reply_target_handle):
    """One Gemini call that judges relevance, writes a post, and writes a reply."""
    news_text = "\n".join(
        f"{i+1}. {a['title']}: {a['summary']}" for i, a in enumerate(articles[:15])
    )

    reply_section = ""
    if reply_target_text:
        reply_section = f"""
SEPARATELY, here is a post by @{reply_target_handle} to also reply to:
"{reply_target_text}"
"""

    prompt = f"""You write the Bluesky account for Fault Lines, a newsletter about the geopolitics of business.

{VOICE_GUIDE}

Here are today's news headlines. Ignore any that aren't about tech geopolitics, trade, supply chains,
sanctions, semiconductors, critical infrastructure, or great power competition over business and technology:

{news_text}
{reply_section}

Do two things:

1. Pick the single most interesting, relevant story above and write ONE original Bluesky post about it,
   under 280 characters. Find a surprising angle, not the obvious headline take.

2. {"Write a thoughtful, substantive reply to the quoted post, under 280 characters. Add a genuine fact, a different angle, or a sharp question. Don't just agree or compliment." if reply_target_text else "Return an empty string for this."}

Return ONLY valid JSON, no markdown, no explanation, in this exact format:
{{"post": "your post text", "reply": "your reply text or empty string"}}"""

    response = call_gemini_with_retry(prompt)
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
        return {
            "post": data.get("post", "")[:300],
            "reply": data.get("reply", "")[:300],
        }
    except Exception as e:
        print(f"JSON parse error: {e}, raw: {text[:300]}")
        return {"post": "", "reply": ""}


def run_bluesky():
    print("Starting Bluesky daily run...")

    client = BlueskyClient()
    if not client.login():
        print("Could not log in to Bluesky, aborting.")
        return

    print("Scraping headlines...")
    articles = scrape_headlines()
    print(f"Got {len(articles)} headlines")

    print("Finding a post to potentially reply to...")
    trending = client.get_trending_posts(limit=15)
    reply_target = pick_post_to_reply_to(trending)

    reply_target_text = ""
    reply_target_handle = ""
    if reply_target:
        reply_target_text = reply_target.get("record", {}).get("text", "")
        reply_target_handle = reply_target.get("author", {}).get("handle", "")

    print("Calling Gemini once for post and reply...")
    result = generate_post_and_reply(articles, reply_target_text, reply_target_handle)

    if result["post"]:
        print(f"Posting: {result['post']}")
        client.post(result["post"])
    else:
        print("No post generated, skipping.")

    time.sleep(5)

    if result["reply"] and reply_target:
        post_uri = reply_target.get("uri")
        post_cid = reply_target.get("cid")
        if post_uri and post_cid:
            print(f"Replying to @{reply_target_handle}: {result['reply']}")
            client.reply(result["reply"], parent_uri=post_uri, parent_cid=post_cid)
    else:
        print("No reply to send, skipping.")

    time.sleep(5)

    print("Looking for accounts to follow...")
    followed_count = client.find_and_follow_relevant_accounts(trending, max_follows=3)
    print(f"Followed {followed_count} new accounts")

    print("Bluesky daily run complete.")


if __name__ == "__main__":
    run_bluesky()
