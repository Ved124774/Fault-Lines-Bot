"""
bluesky_bot.py
--------------
Daily Bluesky activity for Fault Lines:
  1. Write and post one sharp, original take on today's news
  2. Find a genuinely good post about tech geopolitics and reply with a
     thoughtful comment
  3. Follow a small number of accounts that post substantive content on
     the topic
"""

import os
import json
import time
import google.generativeai as genai

from scraper import get_articles
from memory import get_all_memory, format_memory_for_prompt
from bluesky_client import BlueskyClient

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

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


def generate_daily_post(articles, memory) -> str:
    past_context = format_memory_for_prompt(memory)
    news_text = "\n".join(f"• {a['title']}: {a['summary']}" for a in articles[:10])

    prompt = f"""You write the Bluesky account for Fault Lines, a newsletter about the geopolitics of business.

{VOICE_GUIDE}

{past_context}

Today's news:
{news_text}

Write ONE Bluesky post, under 280 characters, about the single most interesting story above.
Pick a genuinely surprising angle, not the obvious headline take. Make it feel like an observation
a smart person would actually post, not a summary.

Return ONLY the post text, nothing else. No quotation marks around it."""

    response = model.generate_content(prompt)
    text = response.text.strip().strip('"')
    return text[:300]


def generate_reply(post_text: str, author_handle: str, memory) -> str:
    past_context = format_memory_for_prompt(memory)

    prompt = f"""You write the Bluesky account for Fault Lines, a newsletter about the geopolitics of business.

{VOICE_GUIDE}

{past_context}

You're replying to this post by @{author_handle}:
"{post_text}"

Write a thoughtful, substantive reply, under 280 characters. Add something genuinely useful: a fact
they might not know, a different angle, a sharp question, or a connection to something else going on.
Don't just agree or compliment them. Don't be combative either. Be the kind of reply that makes someone
go check out your profile.

Return ONLY the reply text, nothing else."""

    response = model.generate_content(prompt)
    text = response.text.strip().strip('"')
    return text[:300]


def pick_best_post_to_reply_to(posts: list) -> dict | None:
    """Use Gemini to pick the single most interesting, substantive post to engage with."""
    if not posts:
        return None

    numbered = "\n".join(
        f"{i+1}. @{p.get('author', {}).get('handle', '?')}: "
        f"{p.get('record', {}).get('text', '')[:200]}"
        for i, p in enumerate(posts)
    )

    prompt = f"""Here are recent Bluesky posts about tech geopolitics:

{numbered}

Pick the ONE post that is most substantive, specific, and worth a thoughtful reply from an expert
account. Avoid posts that are just links with no commentary, or posts that are too short to engage
with meaningfully.

Return ONLY the number of your choice, nothing else."""

    try:
        response = model.generate_content(prompt)
        index = int(response.text.strip())
        if 1 <= index <= len(posts):
            return posts[index - 1]
    except Exception as e:
        print(f"  Pick post error: {e}")

    # Fallback: pick the longest post as a proxy for substance
    return max(posts, key=lambda p: len(p.get("record", {}).get("text", "")))


def run_bluesky():
    print("Starting Bluesky daily run...")

    client = BlueskyClient()
    if not client.login():
        print("Could not log in to Bluesky, aborting.")
        return

    print("Loading 30-day memory...")
    memory = get_all_memory()

    # ── 1. Post original content ────────────────────────────────────────────
    print("Scraping news for today's post...")
    articles = get_articles(max_relevant=15)

    if articles:
        post_text = generate_daily_post(articles, memory)
        print(f"Generated post: {post_text}")
        client.post(post_text)
    else:
        print("No relevant articles found today, skipping original post.")

    time.sleep(3)

    # ── 2. Reply to one good post in the wild ───────────────────────────────
    print("Searching Bluesky for posts to engage with...")
    trending = client.get_trending_posts(limit=20)
    print(f"Found {len(trending)} candidate posts")

    best_post = pick_best_post_to_reply_to(trending)
    if best_post:
        author_handle = best_post.get("author", {}).get("handle", "unknown")
        post_text = best_post.get("record", {}).get("text", "")
        post_uri = best_post.get("uri")
        post_cid = best_post.get("cid")

        if post_uri and post_cid:
            reply_text = generate_reply(post_text, author_handle, memory)
            print(f"Replying to @{author_handle}: {reply_text}")
            client.reply(reply_text, parent_uri=post_uri, parent_cid=post_cid)
        else:
            print("Selected post missing uri/cid, skipping reply.")
    else:
        print("No suitable post found to reply to.")

    time.sleep(3)

    # ── 3. Follow a few relevant accounts ───────────────────────────────────
    print("Looking for accounts to follow...")
    followed_count = client.find_and_follow_relevant_accounts(trending, max_follows=5)
    print(f"Followed {followed_count} new accounts")

    print("Bluesky daily run complete.")


if __name__ == "__main__":
    run_bluesky()
