import feedparser
import requests
import logging
import os
from datetime import datetime, timedelta
import random

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

RSS_FEEDS = {
    "ai_companies": [
        "https://openai.com/blog/rss.xml",
        "https://www.anthropic.com/rss.xml",
        "https://deepmind.google/blog/rss.xml",
        "https://ai.meta.com/blog/rss/",
    ],
    "india_tech": [
        "https://yourstory.com/tag/artificial-intelligence/feed",
        "https://inc42.com/feed/",
    ],
    "dev_builds": [
        "https://hnrss.org/show?points=50",
        "https://dev.to/feed/tag/ai",
        "https://towardsdatascience.com/feed",
    ]
}

def fetch_feed_items(url: str, max_items: int = 3) -> list:
    try:
        feed = feedparser.parse(url)
        items = []
        cutoff = datetime.now() - timedelta(days=1)

        for entry in feed.entries[:max_items * 2]:
            title = entry.get('title', '').strip()
            link = entry.get('link', '')
            summary = entry.get('summary', entry.get('description', ''))[:300]

            if not title or not link:
                continue

            items.append({
                'title': title,
                'link': link,
                'summary': summary
            })

            if len(items) >= max_items:
                break

        return items
    except Exception as e:
        logger.error(f"Error fetching feed {url}: {e}")
        return []

def summarize_with_groq(items: list, category: str) -> str:
    if not items:
        return None

    content = "\n".join([
        f"- {item['title']}: {item['summary']}"
        for item in items
    ])

    prompt = f"""Summarize these {category} news items for an AI/ML student in India.
For each item write exactly one bullet point: start with the key insight, keep it under 20 words, be specific not vague.
Return only the bullet points, no headers, no intro text.

News items:
{content}"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "max_tokens": 300,
                "temperature": 0.3,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=15
        )
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Groq summarization failed: {e}")
        return None

def fetch_daily_brief() -> str:
    message = "📰 *Daily AI/ML Brief*\n\n"
    sections = {
    "🤖 AI Companies": "ai_companies",
    "🇮🇳 India Tech": "india_tech",
    "🛠 Dev Builds": "dev_builds"
    }

    any_content = False

    for header, category in sections.items():
        feeds = RSS_FEEDS[category]
        all_items = []

        for feed_url in feeds:
            items = fetch_feed_items(feed_url, max_items=2)
            all_items.extend(items)
            if len(all_items) >= 3:
                break

        if not all_items:
            continue

        summary = summarize_with_groq(all_items[:3], category)
        if summary:
            message += f"*{header}*\n{summary}\n\n"
            any_content = True

    if not any_content:
        return None

    message += "_Sources: OpenAI, Anthropic, DeepMind, Meta AI, YourStory, Inc42, HN, Dev.to_"
    return message