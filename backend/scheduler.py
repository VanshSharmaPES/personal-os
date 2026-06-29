import os
import logging
import requests
from datetime import datetime, date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from db import (
    get_pending_applications, get_upcoming_deadlines,
    nudge_already_sent, mark_nudge_sent, upsert_activity
)
from github_monitor import get_latest_commit_date
from news_fetcher import fetch_daily_brief, generate_post_idea

load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")


def send_telegram_message(text: str):
    if not TELEGRAM_CHAT_ID or not TELEGRAM_TOKEN:
        logger.error("Telegram credentials not set")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown"
            },
            timeout=10
        )
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")


async def send_morning_digest():
    logger.info("Running morning digest...")
    today = date.today()
    next_7_days = today + timedelta(days=7)

    applications = get_pending_applications()
    all_deadlines = get_upcoming_deadlines()
    upcoming_deadlines = [d for d in all_deadlines if d[2] <= next_7_days]

    message = f"☀️ *Good morning! PersonalOS Daily Digest*\n_{today.strftime('%A, %B %d')}_\n\n"

    message += f"📋 *Applications* ({len(applications)} pending):\n"
    if applications:
        for app in applications[:5]:
            app_id, company, role, date_applied, follow_up_date = app
            days_until_followup = (follow_up_date - today).days
            if days_until_followup <= 0:
                flag = "🔴 Follow-up overdue"
            elif days_until_followup <= 2:
                flag = f"🟡 Follow-up in {days_until_followup}d"
            else:
                flag = f"🟢 Follow-up in {days_until_followup}d"
            message += f"  • {company} — {role} ({flag})\n"
        if len(applications) > 5:
            message += f"  ... and {len(applications) - 5} more\n"
    else:
        message += "  No pending applications\n"
    message += "\n"

    message += f"📅 *Deadlines this week* ({len(upcoming_deadlines)}):\n"
    if upcoming_deadlines:
        for d in upcoming_deadlines:
            deadline_id, title, due_date, category = d
            days_left = (due_date - today).days
            if days_left == 0:
                flag = "🔴 Due TODAY"
            elif days_left <= 2:
                flag = f"🔴 {days_left}d left"
            elif days_left <= 4:
                flag = f"🟡 {days_left}d left"
            else:
                flag = f"🟢 {days_left}d left"
            message += f"  • {title} ({category}) — {flag}\n"
    else:
        message += "  No deadlines this week\n"

    send_telegram_message(message)


async def check_followups():
    logger.info("Checking application follow-ups...")
    today = date.today()
    applications = get_pending_applications()

    for app in applications:
        app_id, company, role, date_applied, follow_up_date = app
        if follow_up_date <= today:
            if not nudge_already_sent(app_id, 'application', 'followup_7d'):
                message = (
                    f"🔔 *Follow-up Reminder*\n\n"
                    f"You applied to *{company}* for *{role}*.\n"
                    f"It's been 7+ days — time to follow up!\n\n"
                    f"Update status: reply with 'Got [status] from {company}'\n"
                    f"or use /status {app_id} [rejected|offer|interview|ghosted]"
                )
                send_telegram_message(message)
                mark_nudge_sent(app_id, 'application', 'followup_7d')


async def check_deadline_reminders():
    logger.info("Checking deadline reminders...")
    today = date.today()
    deadlines = get_upcoming_deadlines()

    for deadline in deadlines:
        deadline_id, title, due_date, category = deadline
        days_left = (due_date - today).days

        nudge_map = {
            7: 'due_7d',
            3: 'due_3d',
            1: 'due_1d',
            0: 'due_today'
        }

        if days_left in nudge_map:
            nudge_type = nudge_map[days_left]
            if not nudge_already_sent(deadline_id, 'deadline', nudge_type):
                if days_left == 0:
                    urgency = "🔴 Due *TODAY*"
                elif days_left == 1:
                    urgency = "🔴 Due *tomorrow*"
                elif days_left == 3:
                    urgency = "🟡 Due in *3 days*"
                else:
                    urgency = "🟢 Due in *7 days*"

                message = (
                    f"⏰ *Deadline Reminder*\n\n"
                    f"{urgency}\n"
                    f"*{title}* ({category})\n"
                    f"Due: {due_date.strftime('%B %d, %Y')}\n\n"
                    f"Mark as done: /done {deadline_id}"
                )
                send_telegram_message(message)
                mark_nudge_sent(deadline_id, 'deadline', nudge_type)


async def check_github_activity():
    logger.info("Checking GitHub activity...")
    if not GITHUB_USERNAME:
        return

    latest_commit = get_latest_commit_date(GITHUB_USERNAME)
    today = date.today()

    if latest_commit:
        upsert_activity(latest_commit, None)
        days_since = (today - latest_commit).days
        if days_since >= 5:
            if not nudge_already_sent(0, 'github', f'inactive_{today.isoformat()}'):
                post_idea = generate_post_idea(GITHUB_USERNAME)
                message = (
                    f"👨‍💻 *GitHub Activity Alert*\n\n"
                    f"No commits in *{days_since} days*.\n"
                    f"Last commit: {latest_commit.strftime('%B %d, %Y')}\n\n"
                    f"💡 *LinkedIn post idea:*\n"
                    f"_{post_idea}_"
                )
                send_telegram_message(message)
                mark_nudge_sent(0, 'github', f'inactive_{today.isoformat()}')
    else:
        logger.info("Could not fetch GitHub commit date")


async def send_daily_brief():
    logger.info("Fetching daily AI/ML brief...")
    try:
        brief = fetch_daily_brief()
        if brief:
            send_telegram_message(brief)
        else:
            logger.info("No content fetched for daily brief")
    except Exception as e:
        logger.error(f"Daily brief failed: {e}")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    scheduler.add_job(
        send_morning_digest,
        'cron',
        hour=8,
        minute=0,
        id='morning_digest'
    )

    scheduler.add_job(
        check_followups,
        'interval',
        hours=6,
        id='check_followups'
    )

    scheduler.add_job(
        check_deadline_reminders,
        'interval',
        hours=6,
        id='check_deadline_reminders'
    )

    scheduler.add_job(
        check_github_activity,
        'cron',
        hour=10,
        minute=0,
        id='check_github'
    )

    scheduler.add_job(
        send_daily_brief,
        'cron',
        hour=9,
        minute=0,
        id='daily_brief'
    )

    return scheduler