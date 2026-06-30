"""
bluesky_bot.py
--------------
Daily Bluesky activity for Fault Lines. Designed to make exactly ONE Gemini
call per run to stay comfortably within free tier rate limits.
"""

import os
import json
import time
import google.generativeai as genai

from scraper import scrape_raw_articles, call_gemini_with_retry
from memory import get_all_memory, format_memory_for_prompt
from bluesky_client import BlueskyClient

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

VOICE_GUIDE = """
VOICE RULES:
- Sound like a sharp, curious person who actually finds this stuff fascinating, not a brand account.
- Plain language, no jargon without explanation.
- A little dry humour is good. Don't force it.
- NEVER use em dashes (—). Use commas or periods instead.
- Vary sentence rhythm, avoid sounding uniform or robotic.
- No hashtags. No "thread below". No corporate phrasing.
- Be specific. Reference an actual fact, company, or country, not vague generalities.
"""


def pick_post_to_reply_to(posts: list):
    """Pick the most substantive post by length, no Gemini call needed."""
    if not posts:
        return None
    candidates = [p for p in posts if len(p.get("record", {}).get("text", "")) > 100]
    if not candidates:
        candidates = posts
    return max(candidates, key=lambda p: len(p.get("record", {}).get("text", "")))


def generate_everything_in_one_call(articles, memory, reply_target_text, reply_target_handle):
    """
    Single Gemini call that does two jobs at once:
      1. Picks the most interesting article and writes an original post about it
      2. Writes a thoughtful reply to a specific trending post
    Returns a dict with 'post' and 'reply' keys.
    """
    past_context = format_memory_for_prompt(memory)
    news_text = "\n".join(
        f"{i+1}. {a['title']}: {a['summary'][:150]}" for i, a in enumerate(articles[:15])
    )

    reply_section = ""
    if reply_target_text:
        reply_section = f"""
SEPARATELY, here is a post by @{reply_target_handle} that you'll also reply to:
"{reply_target_text}"
"""

    prompt = f"""You write the Bluesky account for Fault Lines, a newsletter about the geopolitics of business.

{VOICE_GUIDE}

{past_context}

Here is a numbered list of today's news headlines. Some may not be relevant to tech geopolitics,
business, trade, supply chains, or great power competition, ignore those:

{news_text}
{reply_section}

Do two things:

1. Pick the single most interesting, relevant story from the list above and write ONE original
   Bluesky post about it, under 280 characters. Pick a surprising angle, not the obvious headline.

2. {"Write a thoughtful, substantive reply to the post quoted above, under 280 characters. Add something genuinely useful, a fact, a different angle, or a sharp question. Don't just agree or compliment." if reply_target_text else "Skip this, return an empty string."}

Return ONLY valid JSON in this exact format, nothing else, no markdown:
{{"post": "your original post text here", "reply": "your reply text here or empty string"}}"""

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
        print(f"  JSON parse error: {e}, raw: {text[:200]}")
        return {"post": "", "reply": ""}


def run_bluesky():
    print("Starting Bluesky daily run...")

    client = BlueskyClient()
    if not client.login():
        print("Could not log in to Bluesky, aborting.")
        return

    print("Loading 30-day memory...")
    memory = get_all_memory()

    print("Scraping news (no Gemini call yet)...")
    raw_articles = scrape_raw_articles(max_per_feed=3)
    print(f"Got {len(raw_articles)} raw articles")

    print("Finding a trending post to potentially reply to...")
    trending = client.get_trending_posts(limit=20)
    reply_target = pick_post_to_reply_to(trending)

    reply_target_text = ""
    reply_target_handle = ""
    if reply_target:
        reply_target_text = reply_target.get("record", {}).get("text", "")
        reply_target_handle = reply_target.get("author", {}).get("handle", "")

    print("Calling Gemini once for both the post and the reply...")
    result = generate_everything_in_one_call(
        raw_articles, memory, reply_target_text, reply_target_handle
    )

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
        print("No reply generated or no target, skipping.")

    time.sleep(5)

    print("Looking for accounts to follow...")
    followed_count = client.find_and_follow_relevant_accounts(trending, max_follows=5)
    print(f"Followed {followed_count} new accounts")

    print("Bluesky daily run complete.")


if __name__ == "__main__":
    run_bluesky()
