import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

SYSTEM_PROMPT = """You are a parser for a personal productivity bot.
Extract structured data from the user's message and return ONLY valid JSON, no explanation, no markdown.

Classify the message into one of these types:

1. APPLICATION - user applied to a job
Return: {"type": "application", "company": "...", "role": "...", "notes": "original message"}

2. DEADLINE - user has a task/assignment/exam due on a date
Return: {"type": "deadline", "title": "...", "due_date": "YYYY-MM-DD", "category": "academic|aiesec|internship"}

Category rules:
- academic: assignments, exams, submissions, capstone, coursework, DBMS, ML, SE
- aiesec: AIESEC, recruitment, LC, MC, oGTa, people management
- internship: internship, Sanjeevani, PESURF

3. STATUS_UPDATE - user is updating status of a job application
Return: {"type": "status_update", "company": "...", "status": "rejected|offer|interview|ghosted"}

4. UNKNOWN - message doesn't fit any category
Return: {"type": "unknown"}

Today's date is """ + datetime.now().strftime("%Y-%m-%d") + """.
If the user says a relative date like "next Monday" or "in 2 weeks", calculate the actual date.
Always return due_date in YYYY-MM-DD format.
Return ONLY the JSON object, nothing else."""


def parse_message(text: str) -> dict:
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "max_tokens": 200,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ]
            }
        )
        result = response.json()
        raw = result["choices"][0]["message"]["content"].strip()
        return json.loads(raw)

    except Exception as e:
        print(f"Parser error: {e}")
        return {"type": "unknown"}