import logging
import os
from datetime import datetime
from aiohttp import web
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import (
    get_connection, add_application, add_deadline, get_pending_applications,
    get_upcoming_deadlines, update_application_status, nudge_already_sent,
    mark_nudge_sent, get_latest_activity, upsert_activity, find_applications_by_company
)
from parser import parse_message
from scheduler import create_scheduler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_CHAT_ID = None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TELEGRAM_CHAT_ID
    TELEGRAM_CHAT_ID = update.effective_chat.id
    logger.info(f"Chat ID received: {TELEGRAM_CHAT_ID}")

    welcome_message = """
🤖 *Welcome to PersonalOS Agent!*

I help you track:
- Job applications
- Academic/AIESEC/internship deadlines
- GitHub activity (automated)
- Daily AI/ML news brief

*How to use — just message me:*
  • "Applied to VectorShift for ML Engineer"
  • "Capstone submission on 15th July 2026"
  • "Got rejected from Peakflo"
  • "Peakflo gave me an offer"

*Commands:*
/applications — View pending applications
/deadlines — View upcoming deadlines
/status [id] [status] — Manually update application status
/done [id] — Mark a deadline as completed
/summary — Full digest of everything
/brief — Get today's AI/ML news brief
    """
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def applications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    applications = get_pending_applications()

    if not applications:
        await update.message.reply_text("📭 No pending applications found.")
        return

    message = "📋 *Pending Applications:*\n\n"
    for app in applications:
        app_id, company, role, date_applied, follow_up_date = app
        message += f"*ID:* {app_id}\n"
        message += f"*Company:* {company}\n"
        message += f"*Role:* {role}\n"
        message += f"*Applied:* {date_applied.strftime('%Y-%m-%d')}\n"
        message += f"*Follow-up:* {follow_up_date.strftime('%Y-%m-%d')}\n\n"

    await update.message.reply_text(message, parse_mode='Markdown')


async def deadlines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    deadlines = get_upcoming_deadlines()

    if not deadlines:
        await update.message.reply_text("📭 No upcoming deadlines found.")
        return

    message = "📅 *Upcoming Deadlines:*\n\n"
    for deadline in deadlines:
        deadline_id, title, due_date, category = deadline
        days_left = (due_date - datetime.now().date()).days
        message += f"*ID:* {deadline_id}\n"
        message += f"*Title:* {title}\n"
        message += f"*Category:* {category}\n"
        message += f"*Due:* {due_date.strftime('%Y-%m-%d')} ({days_left} days left)\n\n"

    await update.message.reply_text(message, parse_mode='Markdown')


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ Usage: /status [id] [status]\n"
            "Valid statuses: rejected, offer, interview, ghosted\n"
            "Example: /status 1 rejected"
        )
        return

    try:
        app_id = int(context.args[0])
        status = context.args[1].lower()

        valid_statuses = ['rejected', 'offer', 'interview', 'ghosted']
        if status not in valid_statuses:
            await update.message.reply_text(
                f"❌ Invalid status. Valid options: {', '.join(valid_statuses)}"
            )
            return

        update_application_status(app_id, status)
        await update.message.reply_text(
            f"✅ Application #{app_id} status updated to '{status}'"
        )
    except ValueError:
        await update.message.reply_text("❌ Application ID must be a number.")
    except Exception as e:
        logger.error(f"Error updating application status: {e}")
        await update.message.reply_text("❌ Failed to update application status.")


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ Usage: /done [id]\n"
            "Example: /done 1"
        )
        return

    try:
        deadline_id = int(context.args[0])
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE deadlines SET status = 'done' WHERE id = %s",
            (deadline_id,)
        )
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"✅ Deadline #{deadline_id} marked as done!")
    except ValueError:
        await update.message.reply_text("❌ Deadline ID must be a number.")
    except Exception as e:
        logger.error(f"Error marking deadline as done: {e}")
        await update.message.reply_text("❌ Failed to mark deadline as done.")


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    applications = get_pending_applications()
    deadlines = get_upcoming_deadlines()
    activity = get_latest_activity()

    message = "📊 *PersonalOS Summary*\n\n"

    message += f"📋 *Applications* ({len(applications)} pending):\n"
    if applications:
        for app in applications[:5]:
            app_id, company, role, date_applied, follow_up_date = app
            message += f"  • {app_id}: {company} — {role} (Follow-up: {follow_up_date.strftime('%m/%d')})\n"
        if len(applications) > 5:
            message += f"  ... and {len(applications) - 5} more\n"
    else:
        message += "  None\n"
    message += "\n"

    message += f"📅 *Deadlines* ({len(deadlines)} upcoming):\n"
    if deadlines:
        for deadline in deadlines[:5]:
            deadline_id, title, due_date, category = deadline
            days_left = (due_date - datetime.now().date()).days
            message += f"  • {deadline_id}: {title} ({category}) — {due_date.strftime('%m/%d')} ({days_left} days)\n"
        if len(deadlines) > 5:
            message += f"  ... and {len(deadlines) - 5} more\n"
    else:
        message += "  None\n"
    message += "\n"

    message += "📱 *Activity:*\n"
    if activity:
        github_date, linkedin_date, checked_at = activity
        github_str = github_date.strftime('%m/%d/%Y') if github_date else "No commits tracked yet"
        linkedin_str = linkedin_date.strftime('%m/%d/%Y') if linkedin_date else "Not tracked"
        message += f"  • GitHub: {github_str}\n"
        message += f"  • LinkedIn: {linkedin_str}\n"
        message += f"  • Last checked: {checked_at.strftime('%m/%d/%Y %H:%M')}\n"
    else:
        message += "  No activity data yet\n"

    await update.message.reply_text(message, parse_mode='Markdown')


async def brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching today's AI/ML brief... ⏳")
    from news_fetcher import fetch_daily_brief
    brief = fetch_daily_brief()
    if brief:
        await update.message.reply_text(brief, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Could not fetch news right now. Try again later.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TELEGRAM_CHAT_ID

    if TELEGRAM_CHAT_ID is None:
        TELEGRAM_CHAT_ID = update.effective_chat.id
        logger.info(f"Chat ID received from message: {TELEGRAM_CHAT_ID}")

    text = update.message.text
    logger.info(f"Received message: {text}")

    result = parse_message(text)
    logger.info(f"Parsed result: {result}")

    if result['type'] == 'application':
        try:
            app_id = add_application(
                result['company'],
                result['role'],
                result.get('notes')
            )
            await update.message.reply_text(
                f"✅ Application saved!\n"
                f"Company: {result['company']}\n"
                f"Role: {result['role']}\n"
                f"Follow-up reminder in 7 days (ID: {app_id})"
            )
        except Exception as e:
            logger.error(f"Error saving application: {e}")
            await update.message.reply_text("❌ Failed to save application. Please try again.")

    elif result['type'] == 'deadline':
        try:
            deadline_id = add_deadline(
                result['title'],
                result['due_date'],
                result['category']
            )
            await update.message.reply_text(
                f"✅ Deadline saved!\n"
                f"Title: {result['title']}\n"
                f"Due: {result['due_date']}\n"
                f"Category: {result['category']} (ID: {deadline_id})"
            )
        except Exception as e:
            logger.error(f"Error saving deadline: {e}")
            await update.message.reply_text("❌ Failed to save deadline. Please try again.")

    elif result['type'] == 'status_update':
        try:
            matches = find_applications_by_company(result['company'])
            if not matches:
                await update.message.reply_text(
                    f"❌ No active applications found for '{result['company']}'.\n"
                    f"Use /applications to see all tracked applications."
                )
            elif len(matches) == 1:
                app = matches[0]
                update_application_status(app[0], result['status'])
                await update.message.reply_text(
                    f"✅ Updated!\n"
                    f"Company: {app[1]}\n"
                    f"Role: {app[2]}\n"
                    f"Status: {result['status']}"
                )
            else:
                msg = f"Found multiple applications for '{result['company']}':\n\n"
                for app in matches:
                    msg += f"ID {app[0]}: {app[1]} — {app[2]} (currently: {app[3]})\n"
                msg += f"\nUse /status [id] {result['status']} to update the right one."
                await update.message.reply_text(msg)
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            await update.message.reply_text("❌ Failed to update status.")

    else:
        await update.message.reply_text(
            "🤔 I didn't understand that. Try messages like:\n\n"
            "• \"Applied to VectorShift for ML Engineer\"\n"
            "• \"Capstone submission on 15th July 2026\"\n"
            "• \"Got rejected from Peakflo\"\n\n"
            "Or use /applications, /deadlines, /summary, /brief"
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")


def run_health_server():
    async def health(request):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", health)

    async def start():
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
        await site.start()

    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(start())
    loop.run_forever()


def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("applications", applications_command))
    application.add_handler(CommandHandler("deadlines", deadlines_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("brief", brief_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started")

    logger.info("Starting PersonalOS Agent bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()