import logging
import os
from datetime import datetime
from aiohttp import web
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Import local modules
from db import (
    get_connection, add_application, add_deadline, get_pending_applications,
    get_upcoming_deadlines, update_application_status, nudge_already_sent,
    mark_nudge_sent, get_latest_activity, upsert_activity
)
from parser import parse_message

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variable to store the chat ID for sending nudges and summaries
TELEGRAM_CHAT_ID = None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the command /start is issued."""
    global TELEGRAM_CHAT_ID

    # Store the chat ID for later use
    TELEGRAM_CHAT_ID = update.effective_chat.id
    logger.info(f"Chat ID received: {TELEGRAM_CHAT_ID}")

    welcome_message = """
🤖 *Welcome to PersonalOS Agent!*

I help you track:
• Job applications (via Telegram)
• Academic/AIESEC/internship deadlines (via Telegram)
• GitHub & LinkedIn activity (automated monitoring)

*How to use:*
• Send me messages like:
  - "Applied to VectorShift for ML Engineer role"
  - "Capstone Submission due July 15 2026"
  - "Got rejected from Peakflo"

*Available commands:*
/applications - View pending applications
/deadlines - View upcoming deadlines
/status [id] [status] - Update application status
/done [id] - Mark a deadline as completed
/summary - Get a full digest of everything

I'll automatically:
• Nudge you for follow-ups on applications (7 days)
• Remind you of deadlines (7d/3d/1d before)
• Alert you if GitHub/LinkedIn inactive
• Suggest LinkedIn post ideas when needed

Start tracking by sending me a message!
    """
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def applications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all pending applications."""
    applications = get_pending_applications()

    if not applications:
        await update.message.reply_text("📭 No pending applications found.")
        return

    message = "📋 *Pending Applications:*\n\n"
    for app in applications:
        app_id, company, role, date_applied, follow_up_date, notes = app
        message += f"*ID:* {app_id}\n"
        message += f"*Company:* {company}\n"
        message += f"*Role:* {role}\n"
        message += f"*Applied:* {date_applied.strftime('%Y-%m-%d')}\n"
        message += f"*Follow-up:* {follow_up_date.strftime('%Y-%m-%d')}\n"
        if notes:
            message += f"*Notes:* {notes[:100]}{'...' if len(notes) > 100 else ''}\n"
        message += "\n"

    await update.message.reply_text(message, parse_mode='Markdown')

async def deadlines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all pending deadlines."""
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
        message += f"*Due:* {due_date.strftime('%Y-%m-%d')} ({days_left} days left)\n"
        message += "\n"

    await update.message.reply_text(message, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update application status: /status [id] [status]"""
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
            f"✅ Application #{app_id} status updated to '{status}'",
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text("❌ Application ID must be a number.")
    except Exception as e:
        logger.error(f"Error updating application status: {e}")
        await update.message.reply_text("❌ Failed to update application status.")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mark a deadline as done: /done [id]"""
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

        await update.message.reply_text(
            f"✅ Deadline #{deadline_id} marked as done!",
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text("❌ Deadline ID must be a number.")
    except Exception as e:
        logger.error(f"Error marking deadline as done: {e}")
        await update.message.reply_text("❌ Failed to mark deadline as done.")

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send full digest: pending apps + upcoming deadlines + last activity."""
    # Get pending applications
    applications = get_pending_applications()

    # Get upcoming deadlines
    deadlines = get_upcoming_deadlines()

    # Get latest activity
    activity = get_latest_activity()

    message = "📊 *PersonalOS Summary*\n\n"

    # Applications section
    message += f"📋 *Applications* ({len(applications)} pending):\n"
    if applications:
        for app in applications[:5]:  # Show first 5
            app_id, company, role, _, follow_up_date, _ = app
            message += f"  • {app_id}: {company} - {role} (Follow-up: {follow_up_date.strftime('%m/%d')})\n"
        if len(applications) > 5:
            message += f"  ... and {len(applications) - 5} more\n"
    else:
        message += "  None\n"
    message += "\n"

    # Deadlines section
    message += f"📅 *Deadlines* ({len(deadlines)} upcoming):\n"
    if deadlines:
        for deadline in deadlines[:5]:  # Show first 5
            deadline_id, title, due_date, category = deadline
            days_left = (due_date - datetime.now().date()).days
            message += f"  • {deadline_id}: {title} ({category}) - {due_date.strftime('%m/%d')} ({days_left} days)\n"
        if len(deadlines) > 5:
            message += f"  ... and {len(deadlines) - 5} more\n"
    else:
        message += "  None\n"
    message += "\n"

    # Activity section
    message += "📱 *Activity:*\n"
    if activity:
        activity_id, github_date, linkedin_date, checked_at = activity
        github_str = github_date.strftime('%m/%d/%Y') if github_date else "No commits"
        linkedin_str = linkedin_date.strftime('%m/%d/%Y') if linkedin_date else "No posts"
        message += f"  • GitHub: {github_str}\n"
        message += f"  • LinkedIn: {linkedin_str}\n"
        message += f"  • Last checked: {checked_at.strftime('%m/%d/%Y %H:%M')}\n"
    else:
        message += "  No activity data available\n"

    await update.message.reply_text(message, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command text messages by parsing them."""
    global TELEGRAM_CHAT_ID

    # Store chat ID if not already set
    if TELEGRAM_CHAT_ID is None:
        TELEGRAM_CHAT_ID = update.effective_chat.id
        logger.info(f"Chat ID received from message: {TELEGRAM_CHAT_ID}")
        # In a real deployment, you'd save this to .env or a config file
        # For now, we just log it

    text = update.message.text
    logger.info(f"Received message: {text}")

    # Parse the message
    result = parse_message(text)
    logger.info(f"Parsed result: {result}")

    # Handle based on type
    if result['type'] == 'application':
        try:
            app_id = add_application(
                result['company'],
                result['role'],
                result['notes']
            )
            await update.message.reply_text(
                f"✅ Application saved!\n"
                f"Company: {result['company']}\n"
                f"Role: {result['role']}\n"
                f"Follow-up in 7 days (ID: {app_id})\n"
                f"Use /applications to view all applications",
                parse_mode='Markdown'
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
                f"Category: {result['category']}\n"
                f"(ID: {deadline_id})\n"
                f"Use /deadlines to view all deadlines",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error saving deadline: {e}")
            await update.message.reply_text("❌ Failed to save deadline. Please try again.")

    elif result['type'] == 'status_update':
        await update.message.reply_text(
            f"📝 Status update detected: {result['company']} - {result['status']}\n\n"
            f"To update an application's status, use:\n"
            f"/status [id] [status]\n\n"
            f"Use /applications to see your applications and their IDs\n"
            f"Valid statuses: rejected, offer, interview, ghosted",
            parse_mode='Markdown'
        )

    else:  # unknown
        await update.message.reply_text(
            "🤔 I didn't understand that. Try messages like:\n\n"
            "• \"Applied to VectorShift for ML Engineer role\"\n"
            "• \"Capstone Submission due July 15 2026\"\n"
            "• \"Got rejected from Peakflo\"\n\n"
            "Or use commands like /applications, /deadlines, /summary",
            parse_mode='Markdown'
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
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
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("applications", applications_command))
    application.add_handler(CommandHandler("deadlines", deadlines_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("summary", summary_command))

    # Add message handler for non-command messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Add error handler
    application.add_error_handler(error_handler)

    # Start the Bot
    logger.info("Starting PersonalOS Agent bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()