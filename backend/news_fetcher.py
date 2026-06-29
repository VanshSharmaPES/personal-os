import feedparser
import requests
import logging
import os
from datetime import datetime, timedelta

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


def generate_post_idea(github_username: str) -> str:
    # Step 1: Get latest GitHub activity
    try:
        response = requests.get(
            f"https://api.github.com/users/{github_username}/events/public",
            timeout=10
        )
        events = response.json()

        recent_context = []
        for event in events[:10]:
            if event.get('type') == 'PushEvent':
                repo = event.get('repo', {}).get('name', '').replace(f'{github_username}/', '')
                commits = event.get('payload', {}).get('commits', [])
                for commit in commits[:2]:
                    message = commit.get('message', '').split('\n')[0]
                    if message:
                        recent_context.append(f"Repo: {repo} — Commit: {message}")
            if len(recent_context) >= 3:
                break

        github_context = "\n".join(recent_context) if recent_context else "No recent commits found"

    except Exception as e:
        logger.error(f"GitHub fetch failed: {e}")
        github_context = "Could not fetch GitHub activity"

    # Step 2: Generate post idea with Groq
   

    prompt = f"""You are a LinkedIn ghostwriter for an AI/ML student in India who builds production systems.

    Their recent GitHub activity:
    {github_context}

    Their projects:
    - Sanjeevani AI: two-stage LLM pipeline (Llama 4 Scout for OCR + Llama 3.3 70B for medical analysis), multilingual TTS across 22 Indian languages, rotating API key pool for Groq + NVIDIA NIM, fuzzy matching on 2.5 lakh+ medicine dataset, F1 scores: Medicine 0.809, Overall 0.905
    - ClearTriage: MERN + FastAPI, SHAP-based explainable triage system
    - AlgoForge: Next.js + Supabase + Judge0 + BullMQ, community DSA platform
    - PersonalOS Agent: Telegram bot with NLP parsing, Neon Postgres, APScheduler

    Write a complete LinkedIn post based on their recent GitHub activity and projects.

    Rules:
    - Start with a hook — one punchy line that makes someone stop scrolling
    - 150-200 words total
    - Share one specific technical insight or lesson learned
    - Be first-person, authentic, student builder voice — not corporate
    - Include 1-2 specific numbers or metrics where relevant
    - End with one genuine question to drive comments
    - No generic phrases like "excited to share" or "humbled"
    - No more than 4 hashtags at the end
    - No emojis except sparingly (max 2)

    Return only the post text, nothing else."""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "max_tokens": 100,
                "temperature": 0.9,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=15
        )
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Groq post idea generation failed: {e}")
        return "Could not generate post idea right now. Try again."