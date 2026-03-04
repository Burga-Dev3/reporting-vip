import os
import logging
from datetime import datetime, timedelta
import pytz
import requests

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= BRANDING =================
BRAND_NAME = "Reporting Vip"

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME")

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

EMAIL_RECEIVERS = [
    email.strip()
    for email in os.getenv("EMAIL_RECEIVERS", "").split(",")
    if email.strip()
]

EMAIL_SUBJECT = os.getenv("EMAIL_SUBJECT", "Laporan akun palsu di Telegram")
EMAIL_TEMPLATE = os.getenv("EMAIL_TEMPLATE", "")

# ================= STORAGE =================
approved_users = set()
user_last_report = {}
user_report_count = {}
blocked_users = set()

logging.basicConfig(level=logging.INFO)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    try:
        member = await context.bot.get_chat_member(
            f"@{CHANNEL_USERNAME}",
            user.id
        )

        if member.status in ["left", "kicked"]:
            raise Exception("Not joined")

    except:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")]
        ]

        await update.message.reply_text(
            "⚠️ Anda wajib join channel terlebih dahulu.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await send_welcome(update.message)

# ================= WELCOME =================
async def send_welcome(message):
    user = message.from_user
    wib = pytz.timezone("Asia/Jakarta")
    now = datetime.now(wib).strftime("%d-%m-%Y %H:%M:%S WIB")

    role = "👑 OWNER" if user.id == OWNER_ID else "👤 USER"

    welcome_text = (
        "━━━━━━━━━━━━━━━━━━\n"
        f"🚨 {BRAND_NAME} 🚨\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{role}\n\n"
        f"Nama: {user.full_name}\n"
        f"Username: @{user.username}\n"
        f"ID: {user.id}\n"
        f"Premium: {'Ya ⭐' if user.is_premium else 'Tidak'}\n"
        f"Waktu: {now}"
    )

    keyboard = [
        [
            InlineKeyboardButton("📢 Saluran", url=f"https://t.me/{CHANNEL_USERNAME}"),
            InlineKeyboardButton("☎️ Support", url=f"https://t.me/{SUPPORT_USERNAME}")
        ],
        [
            InlineKeyboardButton("📨 REPORT", callback_data="buat_laporan")
        ]
    ]

    await message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= REPORT BUTTON =================
async def handle_report_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if user.id in blocked_users:
        await query.message.reply_text("🚫 Anda diblokir karena spam.")
        return

    if user.id == OWNER_ID or user.id in approved_users:
        context.user_data["awaiting_report"] = True
        await query.message.reply_text("Kirim username target.\nContoh: @username")
        return

    await query.message.reply_text(
        "⚠️ Anda belum memiliki akses.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Minta Akses", callback_data="request_access")]
        ])
    )

# ================= REQUEST ACCESS =================
async def handle_request_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    await query.message.reply_text("Permintaan dikirim ke owner.")

    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
        ]
    ]

    await context.bot.send_message(
        OWNER_ID,
        f"Permintaan Akses\n\nNama: {user.full_name}\nUsername: @{user.username}\nID: {user.id}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= APPROVE =================
async def handle_owner_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != OWNER_ID:
        return

    action, user_id = query.data.split("_")
    user_id = int(user_id)

    if action == "approve":
        approved_users.add(user_id)
        await context.bot.send_message(user_id, "🎉 Akses disetujui!")
        await query.edit_message_text(f"User {user_id} diapprove.")

    elif action == "reject":
        await context.bot.send_message(user_id, "❌ Akses ditolak.")
        await query.edit_message_text(f"User {user_id} ditolak.")

# ================= HANDLE REPORT =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not context.user_data.get("awaiting_report"):
        return

    now = datetime.now()

    if user.id != OWNER_ID:
        if user.id in user_last_report:
            if now - user_last_report[user.id] < timedelta(minutes=5):
                await update.message.reply_text("⏳ Tunggu 5 menit sebelum membuat laporan lagi.")
                return
        user_last_report[user.id] = now

    if not EMAIL_RECEIVERS:
        await update.message.reply_text("⚠️ Email penerima belum dikonfigurasi.")
        return

    target = update.message.text.strip()

    if user.id not in user_report_count:
        user_report_count[user.id] = 0
    user_report_count[user.id] += 1

    await send_email(target)

    await update.message.reply_text("✅ Laporan berhasil dikirim.")
    context.user_data["awaiting_report"] = False

# ================= SEND EMAIL VIA BREVO =================
async def send_email(target):
    target_clean = target.replace("@", "")

    content = EMAIL_TEMPLATE.format(
        target=target,
        target_clean=target_clean
    )

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    data = {
        "sender": {
            "name": "Reporting Bot",
            "email": SENDER_EMAIL
        },
        "to": [{"email": email} for email in EMAIL_RECEIVERS],
        "subject": EMAIL_SUBJECT,
        "textContent": content
    }

    requests.post(url, headers=headers, json=data)

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_report_button, pattern="buat_laporan"))
    app.add_handler(CallbackQueryHandler(handle_request_access, pattern="request_access"))
    app.add_handler(CallbackQueryHandler(handle_owner_decision, pattern="^(approve_|reject_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
