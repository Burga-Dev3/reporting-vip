
import os
import random
import asyncio
from datetime import datetime

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG (RAILWAY ENV) =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

OWNER_CHANNEL = "https://t.me/jetrolet"
SUPPORT_CONTACT = "https://t.me/burgaa"

RECEIVER_EMAILS = [
    "report@telegram.org",
    "stopCA@telegram.org",
    "recover@telegram.org",
    "sberbank@sberbank.ru",
    "copyright@telegram.org",
    "sms@telegram.org",
    "privacy@telegram.org",
    "abuse@telegram.org",
    "security@telegram.org",
    "info@telegram.org",
]

# ================= HELPER =================

def generate_ticket():
    return ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))

# ================= EMAIL FUNCTION =================

async def kirim_email(target_username):
    ticket = generate_ticket()
    waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    clean_username = target_username.replace("@", "")
    telegram_link = f"https://t.me/{clean_username}"

    # ===== TEXT VERSION =====
    isi_text = f"""
This is a report regarding a Telegram account that is impersonating the official support team of Sberbank (Russia).

Details of the reported account:

- Username: {target_username}
- Profile link: {telegram_link}
- Display name: Sberbank Support / Sber Official Support
- Violation: The account falsely claims to represent Sberbank’s official customer support and may mislead users.

The reported account is not affiliated with the official Sberbank organization and poses a risk of financial harm.

Immediate investigation and enforcement action are requested.

----------------------------------------

Ticket Details:
- Ticket ID: {ticket}
- Time: {waktu}

This email was generated automatically by Reporting Vip system.
"""

    # ===== HTML VERSION =====
    isi_html = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2 style="color:#c62828;">Fake Account Report</h2>

    <p>This is a report regarding a Telegram account impersonating the official support team of <strong>Sberbank (Russia)</strong>.</p>

    <h3>Reported Account Details:</h3>
    <ul>
        <li><strong>Username:</strong> {target_username}</li>
        <li><strong>Profile Link:</strong> <a href="{telegram_link}">{telegram_link}</a></li>
        <li><strong>Display Name:</strong> Sberbank Support / Sber Official Support</li>
        <li><strong>Violation:</strong> Impersonation and possible fraud activity.</li>
    </ul>

    <p>The account is not affiliated with the official Sberbank organization and may cause financial harm.</p>

    <hr>

    <h4>Ticket Information</h4>
    <p>
        <strong>Ticket ID:</strong> {ticket}<br>
        <strong>Time:</strong> {waktu}
    </p>

    <p style="font-size:12px;color:gray;">
        This email was generated automatically by Reporting Vip system.
    </p>
</body>
</html>
"""

    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=RECEIVER_EMAILS,
        subject="Report of Fake Account Impersonating Sberbank Support Team",
        plain_text_content=isi_text,
        html_content=isi_html
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Report sent | Ticket: {ticket} | Status: {response.status_code}")
    except Exception as e:
        print(f"Error sending email: {e}")

# ================= TELEGRAM HANDLER =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    welcome_text = f"""
👋 Welcome to Reporting Vip

Hello {user.first_name}
Username : @{user.username if user.username else 'None'}
User ID  : {user.id}

Click the button below to create a report.
"""

    keyboard = [
        [InlineKeyboardButton("📨 Create Report", callback_data="create_report")],
        [
            InlineKeyboardButton("📢 Owner Channel", url=OWNER_CHANNEL),
            InlineKeyboardButton("🛠 Contact Support", url=SUPPORT_CONTACT),
        ],
    ]

    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_report":
        context.user_data["awaiting_username"] = True
        await query.message.reply_text("Please send the target username (example: @username)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_username"):
        target_username = update.message.text.strip()

        await kirim_email(target_username)

        await update.message.reply_text("✅ Report successfully submitted.")

        context.user_data["awaiting_username"] = False

# ================= MAIN =================

def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN not set!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Reporting Vip Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
