"""
newsletter_bot.py
------------------
Writes and publishes the twice-weekly Fault Lines newsletter issue.
"""

import os
import re
import requests
from datetime import datetime, timezone
import google.generativeai as genai

from scraper import get_articles
from memory import get_all_memory, format_memory_for_prompt

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BEEHIIV_API_KEY = os.environ["BEEHIIV_API_KEY"]
BEEHIIV_PUBLICATION_ID = os.environ["BEEHIIV_PUBLICATION_ID"]

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-pro")

VOICE_GUIDE = """
VOICE AND STYLE RULES — follow these strictly:

- Write like a sharp, curious friend explaining something fascinating over coffee, not a press release
  and not an academic paper.
- Plain language. If a term needs jargon, explain it in one clause, don't assume the reader knows it.
- A hint of dry humour is welcome. Don't force jokes, but a wry observation is good.
- Be opinionated and specific. Avoid vague hedging like "some experts believe" — say what's actually
  going on and why it matters.
- NEVER use em dashes (—) anywhere in the text. Use commas, periods, or parentheses instead.
- Vary sentence length. Short punchy sentences mixed with longer explanatory ones. Avoid a robotic,
  uniform rhythm; that's the easiest way to sound like AI.
- No corporate throat-clearing like "In today's rapidly evolving landscape" or "In an increasingly
  interconnected world." Just start with the actual interesting thing.
- Avoid clichés: "double-edged sword," "elephant in the room," "only time will tell," "game changer."
- Address the reader sometimes, directly, like "you" - this is a newsletter, not a textbook.
- Be curious on the page. Ask a real question sometimes and then answer it.
- Every section should teach the reader something they didn't know, not just summarise news they've
  half-seen already.
"""


def get_past_issues_text(memory: dict) -> str:
    return format_memory_for_prompt(memory)


def generate_newsletter(articles, memory: dict) -> str:
    past_context = get_past_issues_text(memory)
    news_text = "\n".join(
        f"• [{a['source']}] {a['title']}: {a['summary']}" for a in articles
    )
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    prompt = f"""You are the writer of Fault Lines, a twice-weekly newsletter about the geopolitics of business.

{VOICE_GUIDE}

Your readers are smart, curious people, including entrepreneurs and business leaders, but also anyone who
wants to understand how power actually works in the global economy. Your angle: who really controls the
chips, cables, ports, minerals, and infrastructure that the world runs on, and what happens when great
powers fight over it. You have a particular fondness for stories about small countries or unglamorous
companies that turn out to have enormous leverage.

{past_context}

Today's date: {today}

Today's relevant news stories to draw from:
{news_text}

Write a complete newsletter issue in HTML with this structure:

<h1>[A sharp, specific issue title, not generic. Not "Issue 12", an actual headline.]</h1>
<p style="color:#666;font-size:14px;">Fault Lines | {today}</p>
<hr/>

<h2>This Week's Fault Line</h2>
<p>[Lead story, 250-300 words. Pick the single most interesting story today. Open with a hook, not
a date or a fact dump. Explain what happened, why it actually matters to a business reader, and what
the second-order consequence might be that most coverage is missing.]</p>

<h2>The Chokepoints</h2>
<p>[2-3 shorter stories, 100-120 words each, about infrastructure, supply chains, or sanctions. Bold
the headline phrase at the start of each one.]</p>

<h2>The Small Player That Matters</h2>
<p>[120-150 words on one country, company, or institution that most people overlook but that has real
leverage in this week's stories. Make the reader feel like they just learned something genuinely
surprising.]</p>

<h2>The Bottom Line</h2>
<p>[60-80 words. One sharp, memorable takeaway. This is the line readers should forward to a friend.]</p>

<hr/>
<p style="color:#666;font-size:13px;">Fault Lines lands every Wednesday and Sunday. If this was useful,
forward it to someone who'd appreciate it.</p>

Write only the HTML, nothing else. No markdown formatting, no preamble, no explanation of what you did.
Make every sentence earn its place."""

    response = model.generate_content(prompt)
    return response.text.strip().strip("```html").strip("```").strip()


def extract_subject_from_html(html: str) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r"<[^>]+>", "", match.group(1)).strip()
    return f"Fault Lines — {datetime.now(timezone.utc).strftime('%B %d, %Y')}"


def publish_to_beehiiv(html_content: str, subject: str) -> bool:
    url = f"https://api.beehiiv.com/v2/publications/{BEEHIIV_PUBLICATION_ID}/posts"
    headers = {
        "Authorization": f"Bearer {BEEHIIV_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "subject": subject,
        "content_html": html_content,
        "status": "confirmed",
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code in (200, 201):
            post = resp.json().get("data", {})
            print(f"  Newsletter published to beehiiv: {post.get('id')}")
            return True
        print(f"  beehiiv error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"  beehiiv publish error: {e}")
    return False


def run_newsletter():
    print("Starting newsletter generation...")
    articles = get_articles(max_relevant=20)

    print("Loading 30-day memory...")
    memory = get_all_memory()

    print("Writing the issue with Gemini...")
    html = generate_newsletter(articles, memory)
    subject = extract_subject_from_html(html)
    print(f"Generated: {subject}")

    publish_to_beehiiv(html, subject)


if __name__ == "__main__":
    run_newsletter()
