import os
import re
import time
import sqlite3
import logging
import requests
import threading
from queue import Queue
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ================= BRANDING =================

BOT_BRAND = "Reporting Vip"

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

EMAIL_SUBJECT = os.getenv("EMAIL_SUBJECT")
EMAIL_TEMPLATE = os.getenv("EMAIL_TEMPLATE")

CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_URL = os.getenv("CHANNEL_URL")

SUPPORT_URL = os.getenv("SUPPORT_URL")

OWNER_ID = int(os.getenv("OWNER_ID"))

REPORT_DELAY = 60

# ================= VALIDATE ENV =================

required_vars = [
    BOT_TOKEN,
    BREVO_API_KEY,
    EMAIL_SENDER,
    EMAIL_RECEIVER,
    EMAIL_SUBJECT,
    EMAIL_TEMPLATE,
]

if not all(required_vars):
    raise RuntimeError("Beberapa environment variable belum diisi")

# ================= LOGGING =================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

# ================= DATABASE =================

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reports(
case_id TEXT,
target TEXT,
user_id INTEGER,
date TEXT
)
""")

conn.commit()

# ================= MEMORY =================

WAITING_REPORT = set()
LAST_REPORT = {}

# ================= EMAIL QUEUE =================

email_queue = Queue()

# ================= USER STATUS =================

def get_user_status(user_id):

    if user_id == OWNER_ID:
        return "Owner 👑"

    return "Member 👤"

# ================= VALIDATE USERNAME =================

def validate_username(username):
    pattern = r"^@[A-Za-z][A-Za-z0-9_]{4,}$"
    return re.match(pattern, username)

# ================= CASE ID =================

def generate_case():
    return datetime.utcnow().strftime("CASE-%Y%m%d-%H%M%S")

# ================= EMAIL WORKER =================

def email_worker():

    while True:

        content = email_queue.get()

        url = "https://api.brevo.com/v3/smtp/email"

        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }

        data = {
            "sender": {"email": EMAIL_SENDER},
            "to": [{"email": EMAIL_RECEIVER}],
            "subject": EMAIL_SUBJECT,
            "textContent": content
        }

        try:

            r = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=10
            )

            logging.info(f"Email sent status {r.status_code}")

        except Exception as e:

            logging.warning(f"Email failed: {e}")

        email_queue.task_done()

threading.Thread(target=email_worker, daemon=True).start()

# ================= CHANNEL CHECK =================

async def check_join(bot, user_id):

    try:

        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member","administrator","creator"]

    except:
        return False

# ================= PROFILE CARD =================

async def generate_profile_card(bot, user):

    photos = await bot.get_user_profile_photos(user.id, limit=1)

    if photos.total_count == 0:
        return None

    file = await bot.get_file(photos.photos[0][-1].file_id)

    r = requests.get(file.file_path)

    avatar = Image.open(BytesIO(r.content)).convert("RGBA")

    avatar = avatar.resize((300,300))

    width = 900
    height = 450

    bg = Image.new("RGBA",(width,height))
    draw = ImageDraw.Draw(bg)

    for y in range(height):
        r = int(20 + (y/height)*80)
        g = int(20 + (y/height)*40)
        b = int(60 + (y/height)*120)
        draw.line([(0,y),(width,y)],fill=(r,g,b))

    mask = Image.new("L",(300,300),0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0,0,300,300),fill=255)

    avatar_circle = Image.new("RGBA",(300,300))
    avatar_circle.paste(avatar,(0,0),mask)

    bg.paste(avatar_circle,(60,75),avatar_circle)

    frame = ImageDraw.Draw(bg)
    frame.ellipse((55,70,365,380),outline=(255,215,0),width=6)

    try:
        font_big = ImageFont.truetype("arial.ttf",48)
        font_mid = ImageFont.truetype("arial.ttf",26)
        font_small = ImageFont.truetype("arial.ttf",22)
    except:
        font_big = ImageFont.load_default()
        font_mid = ImageFont.load_default()
        font_small = ImageFont.load_default()

    username = user.username if user.username else "None"

    draw.text((420,60),BOT_BRAND,fill=(255,215,0),font=font_big)

    draw.text((420,150),f"Name : {user.first_name}",fill=(255,255,255),font=font_mid)

    draw.text((420,200),f"Username : @{username}",fill=(200,200,200),font=font_small)

    draw.text((420,240),f"User ID : {user.id}",fill=(200,200,200),font=font_small)

    draw.text((420,300),"VIP Reporting System",fill=(180,180,255),font=font_small)

    bio = BytesIO()
    bio.name = "profile_card.png"

    bg.save(bio,"PNG")

    bio.seek(0)

    return bio

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    cursor.execute("INSERT OR IGNORE INTO users VALUES(?)",(user.id,))
    conn.commit()

    joined = await check_join(context.bot,user.id)

    if not joined:

        keyboard = [
            [InlineKeyboardButton("📢 Join Saluran",url=CHANNEL_URL)],
            [InlineKeyboardButton("✅ Saya Sudah Join",callback_data="check_join")]
        ]

        await update.message.reply_text(
            f"🚫 {BOT_BRAND}\n\nKamu harus join saluran terlebih dahulu untuk menggunakan bot ini.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

    status = get_user_status(user.id)

    now = datetime.utcnow()
    date = now.strftime("%Y-%m-%d")

    keyboard = [
        [InlineKeyboardButton("📋 Kirim Laporan",callback_data="report")],
        [
            InlineKeyboardButton("📢 Saluran",url=CHANNEL_URL),
            InlineKeyboardButton("🆘 Support",url=SUPPORT_URL)
        ]
    ]

    photo = await generate_profile_card(context.bot,user)

    text = (
        f"🤖 {BOT_BRAND}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"👋 Selamat datang {user.first_name}\n\n"

        f"👤 Nama : {user.first_name}\n"
        f"🔗 Username : @{user.username if user.username else 'None'}\n"
        f"🆔 ID : {user.id}\n"
        f"📊 Status : {status}\n"
        f"📅 Tanggal : {date}\n\n"

        "🚀 Sistem laporan otomatis aktif\n"
        "📨 Gunakan tombol dibawah untuk mengirim laporan."
    )

    if photo:

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=photo,
            caption=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    else:

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ================= BUTTON =================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "report":

        now = time.time()

        if user_id in LAST_REPORT:

            remaining = REPORT_DELAY - (now - LAST_REPORT[user_id])

            if remaining > 0:

                await query.message.reply_text(
                    f"⏳ {BOT_BRAND}\nTunggu {int(remaining)} detik sebelum laporan berikutnya."
                )
                return

        WAITING_REPORT.add(user_id)

        await query.message.reply_text(
            f"📨 {BOT_BRAND}\n\nKirim username target\n\nContoh:\n@username"
        )

# ================= HANDLE MESSAGE =================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    text = update.message.text

    if user.id not in WAITING_REPORT:
        return

    if not validate_username(text):

        await update.message.reply_text(
            f"❌ {BOT_BRAND}\nUsername tidak valid.\nGunakan format: @username"
        )
        return

    WAITING_REPORT.remove(user.id)

    LAST_REPORT[user.id] = time.time()

    case_id = generate_case()

    now = datetime.utcnow()

    date = now.strftime("%Y-%m-%d")
    time_now = now.strftime("%H:%M:%S")

    target = text.replace("@","")

    email_content = EMAIL_TEMPLATE.format(
        case_id=case_id,
        target=target,
        name=user.first_name,
        username=user.username if user.username else "None",
        user_id=user.id,
        date=date,
        time=time_now
    )

    email_queue.put(email_content)

    cursor.execute(
        "INSERT INTO reports VALUES(?,?,?,?)",
        (case_id,target,user.id,date)
    )

    conn.commit()

    logging.info(f"REPORT {case_id} | USER {user.id} | TARGET @{target}")

    await update.message.reply_text(

        f"✅ {BOT_BRAND}\n\n"
        f"Laporan berhasil dikirim\n\n"
        f"🆔 Case ID : {case_id}\n"
        f"🎯 Target : @{target}\n"
        f"🔗 https://t.me/{target}"
    )

# ================= ERROR HANDLER =================

async def error_handler(update, context):

    logging.error(msg="Exception while handling update:", exc_info=context.error)

# ================= MAIN =================

def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        CallbackQueryHandler(check_join_button,pattern="check_join")
    )

    app.add_handler(CallbackQueryHandler(button))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    app.add_error_handler(error_handler)

    print(f"{BOT_BRAND} berjalan...")

    app.run_polling()

if __name__ == "__main__":
    main()
