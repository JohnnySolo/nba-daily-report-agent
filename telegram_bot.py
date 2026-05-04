"""Telegram bot entry point — wires the NBA agent to Telegram.

Phase A scope: private, whitelist-only bot. Plain-text team queries and
two slash commands (/start, /help). No buttons, no scheduled pushes.

Usage:
    python telegram_bot.py

Environment variables required (in .env):
    ANTHROPIC_API_KEY
    TAVILY_API_KEY
    TELEGRAM_BOT_TOKEN
"""

import logging
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from run import run_report

load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
AUTHORIZED_USER_IDS = {
    8753434841,  # Yoni
}

# Telegram's hard limit per message
TELEGRAM_MESSAGE_LIMIT = 4096

# Logging — INFO level so we can see bot activity without debug noise
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    """Whitelist check. Returns True only for pre-approved user IDs."""
    return user_id in AUTHORIZED_USER_IDS


def split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split a long message into chunks under Telegram's per-message limit.

    Splits on section dividers first (to keep sections intact), falls back
    to paragraph boundaries, and finally to hard character cuts.
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > limit:
        # Prefer splitting on section divider lines
        split_at = remaining.rfind('\n─────', 0, limit)
        if split_at == -1:
            # Fallback: split on double newline (paragraph boundary)
            split_at = remaining.rfind('\n\n', 0, limit)
        if split_at == -1:
            # Last resort: split on any newline
            split_at = remaining.rfind('\n', 0, limit)
        if split_at == -1:
            # No newline found — hard cut at limit
            split_at = limit

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — welcome message."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(
            "This is a private bot. Access is restricted."
        )
        logger.warning(f"Unauthorized /start from user {user_id}")
        return

    welcome = (
        "NBA Daily Report Agent — private access confirmed.\n\n"
        "Send a team name (e.g., Celtics, Lakers, BOS, \"Los Angeles Lakers\") "
        "to generate a full daily report.\n\n"
        "Use /help for more info."
    )
    await update.message.reply_text(welcome)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help — usage instructions."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(
            "This is a private bot. Access is restricted."
        )
        return

    help_text = (
        "How to use this bot:\n\n"
        "Send a team name to generate a daily report. Accepted formats:\n"
        "• Full name: Boston Celtics\n"
        "• City: Boston\n"
        "• Nickname: Celtics\n"
        "• Abbreviation: BOS\n\n"
        "Each report includes:\n"
        "1. Main statistics (traditional + advanced metrics)\n"
        "2. Interesting statistics (outliers + recent trends)\n"
        "3. Scouting report (strengths + weaknesses)\n"
        "4. Key players (top rotation by minutes)\n"
        "5. Injury report (active teams only)\n"
        "6. Credible analytical articles\n\n"
        "Generation takes 30-90 seconds."
    )
    await update.message.reply_text(help_text)


async def handle_team_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain-text messages as team queries."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "unknown"

    if not is_authorized(user_id):
        await update.message.reply_text(
            "This is a private bot. Access is restricted."
        )
        logger.warning(f"Unauthorized query from user {user_id} (@{username})")
        return

    team_query = update.message.text.strip()
    logger.info(f"Authorized query from {user_id}: '{team_query}'")

    # Immediate acknowledgement — user knows the bot is working
    ack_message = await update.message.reply_text(
        f"Generating report for {team_query}... (30-90 seconds)"
    )

    # Show typing indicator during agent execution
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    try:
        report = run_report(team_query)
    except Exception as e:
        logger.error(f"Agent failed for query '{team_query}': {e}")
        await ack_message.edit_text(
            f"Report generation failed. Error logged. Try again in a moment."
        )
        return

    # Send the full report, splitting into multiple messages if too long
    chunks = split_message(report)

    # Edit the acknowledgement to become the first chunk
    try:
        await ack_message.edit_text(chunks[0])
    except Exception as e:
        # Edit failed (rare) — send as new message instead
        logger.warning(f"Edit failed, sending as new message: {e}")
        await update.message.reply_text(chunks[0])

    # Send remaining chunks as follow-ups
    for chunk in chunks[1:]:
        await update.message.reply_text(chunk)

    logger.info(f"Report delivered to {user_id} ({len(chunks)} message(s))")


def main():
    """Start the bot and begin polling for messages."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not found in environment. "
            "Check .env file."
        )

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_team_query))

    logger.info("Bot starting. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()