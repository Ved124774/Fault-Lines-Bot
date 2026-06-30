"""
memory.py
---------
Reads the last 30 days of Fault Lines content so the bot never repeats itself:
  - Past beehiiv newsletter issues
  - Past Bluesky posts from the Fault Lines account
"""

import os
import requests
from datetime import datetime, timezone, timedelta

BEEHIIV_API_KEY = os.environ.get("BEEHIIV_API_KEY", "")
BEEHIIV_PUBLICATION_ID = os.environ.get("BEEHIIV_PUBLICATION_ID", "")
BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")


def get_past_newsletter_issues(days: int = 30, limit: int = 10):
    """Fetch recent confirmed beehiiv posts as context for the next issue."""
    if not BEEHIIV_API_KEY or not BEEHIIV_PUBLICATION_ID:
        return []

    url = f"https://api.beehiiv.com/v2/publications/{BEEHIIV_PUBLICATION_ID}/posts"
    headers = {"Authorization": f"Bearer {BEEHIIV_API_KEY}"}
    params = {"limit": limit, "status": "confirmed"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"  beehiiv fetch error: {resp.status_code}")
            return []

        posts = resp.json().get("data", [])
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = []

        for p in posts:
            pub_ts = p.get("publish_date") or p.get("created_at", 0)
            if isinstance(pub_ts, int) and pub_ts > 0:
                pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
            else:
                continue

            if pub_dt >= cutoff:
                recent.append({
                    "title": p.get("subject", "Untitled"),
                    "preview": p.get("preview_text", ""),
                    "date": pub_dt.strftime("%Y-%m-%d"),
                })

        return recent

    except Exception as e:
        print(f"  beehiiv memory error: {e}")
        return []


def get_bluesky_did(handle: str):
    """Resolve a Bluesky handle to a DID."""
    try:
        resp = requests.get(
            "https://bsky.social/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": handle},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("did")
    except Exception:
        pass
    return None


def get_past_bluesky_posts(days: int = 30, limit: int = 50):
    """Fetch recent posts from the Fault Lines Bluesky account."""
    if not BLUESKY_HANDLE:
        return []

    did = get_bluesky_did(BLUESKY_HANDLE)
    if not did:
        print("  Could not resolve Bluesky DID")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    posts = []

    try:
        cursor = None
        while len(posts) < limit:
            params = {"actor": did, "limit": 50}
            if cursor:
                params["cursor"] = cursor

            resp = requests.get(
                "https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed",
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            feed = data.get("feed", [])
            if not feed:
                break

            stop = False
            for item in feed:
                post = item.get("post", {})
                record = post.get("record", {})
                created = record.get("createdAt", "")
                text = record.get("text", "")

                if created:
                    try:
                        post_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        if post_dt < cutoff:
                            stop = True
                            break
                    except Exception:
                        pass

                if text:
                    posts.append(text)

            if stop:
                break

            cursor = data.get("cursor")
            if not cursor:
                break

    except Exception as e:
        print(f"  Bluesky memory error: {e}")

    return posts[:limit]


def get_all_memory():
    """Return all past content as a single context object."""
    print("  Loading past newsletter issues...")
    newsletter_issues = get_past_newsletter_issues(days=30)
    print(f"  Loaded {len(newsletter_issues)} past issues")

    print("  Loading past Bluesky posts...")
    bluesky_posts = get_past_bluesky_posts(days=30)
    print(f"  Loaded {len(bluesky_posts)} past Bluesky posts")

    return {
        "newsletter_issues": newsletter_issues,
        "bluesky_posts": bluesky_posts,
    }


def format_memory_for_prompt(memory: dict) -> str:
    """Format memory into a string for inclusion in Gemini prompts."""
    lines = []

    if memory.get("newsletter_issues"):
        lines.append("PAST NEWSLETTER ISSUES (do not repeat these topics or angles):")
        for issue in memory["newsletter_issues"]:
            lines.append(f"  [{issue['date']}] {issue['title']} — {issue['preview']}")
        lines.append("")

    if memory.get("bluesky_posts"):
        lines.append("RECENT BLUESKY POSTS (do not repeat these exact angles or facts):")
        for post in memory["bluesky_posts"][:20]:
            lines.append(f"  — {post[:150]}")
        lines.append("")

    return "\n".join(lines)
