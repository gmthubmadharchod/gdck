import os
import asyncio
import threading
import re
from flask import Flask, request, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import qrcode
from docker_handler import DockerExtractor

# ============ CONFIG ============
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
OWNER_ID = int(os.getenv("OWNER_ID"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "owner")
UPI_ID = os.getenv("UPI_ID", "owner@ybl")
PORT = int(os.getenv("PORT", 8080))
# ================================

app = Flask(__name__)

# MongoDB
client_mongo = AsyncIOMotorClient(MONGO_URL)
db = client_mongo["premium_bot"]
premium_col = db["premium_users"]
stats_col = db["user_stats"]

# Docker Handler
docker = DockerExtractor()

# Pyrogram Bot
bot = Client("premium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# User session
user_session = {}

# ============ Database Functions ============
async def is_premium(user_id):
    user = await premium_col.find_one({"user_id": user_id})
    if user and user.get("active"):
        if user["expiry"] > datetime.now():
            return True
    return False

async def add_premium(user_id, days=30):
    expiry = datetime.now() + timedelta(days=days)
    await premium_col.update_one(
        {"user_id": user_id},
        {"$set": {"expiry": expiry, "active": True}},
        upsert=True
    )

async def update_stats(user_id, action):
    await stats_col.update_one(
        {"user_id": user_id},
        {"$inc": {action: 1, "total": 1}},
        upsert=True
    )

def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024*1024:
        return f"{size/1024:.2f} KB"
    else:
        return f"{size/(1024*1024):.2f} MB"

def parse_image_name(text):
    text = text.strip()
    url_pattern = r'https?://hub\.docker\.com/r/([^/]+)/([^/]+)'
    match = re.match(url_pattern, text)
    if match:
        return f"{match.group(1)}/{match.group(2)}:latest"
    if '/' in text or ':' in text:
        return text
    return f"library/{text}:latest"

# ============ Flask Routes ============
@app.route('/')
def home():
    return jsonify({"status": "active", "bot": "Docker Extractor Bot"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

# ============ Bot Commands ============

@bot.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id
    premium = await is_premium(user_id)
    
    text = f"""🔥 Docker Image Extractor Bot

Hi {message.from_user.first_name}!

Commands:
/zip - Extract image to ZIP
/files - Get file list
/upi - Payment info
/premium - Check status
/profile - Your stats

Status: {'✨ Premium' if premium else '⭐ Free'}"""
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Buy Premium", callback_data="buy")]
    ])
    
    await message.reply_text(text, reply_markup=buttons)

@bot.on_message(filters.command("zip"))
async def zip_command(client, message: Message):
    user_id = message.from_user.id
    user_session[user_id] = {"action": "zip", "waiting": True}
    await message.reply_text(
        "🔍 Send me the Docker image name/URL\n\n"
        "Examples:\n"
        "• ubuntu:latest\n"
        "• nginx:alpine\n"
        "• https://hub.docker.com/r/library/ubuntu"
    )

@bot.on_message(filters.command("files"))
async def files_command(client, message: Message):
    user_id = message.from_user.id
    user_session[user_id] = {"action": "files", "waiting": True}
    await message.reply_text(
        "🔍 Send me the Docker image name/URL\n\n"
        "Examples:\n"
        "• ubuntu:latest\n"
        "• nginx:alpine"
    )

@bot.on_message(filters.command("premium"))
async def premium_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id == OWNER_ID and len(message.command) > 2:
        action = message.command[1]
        target = int(message.command[2])
        
        if action == "add":
            days = int(message.command[3]) if len(message.command) > 3 else 30
            await add_premium(target, days)
            await message.reply_text(f"✅ Premium added to {target} for {days} days!")
        elif action == "remove":
            await premium_col.delete_one({"user_id": target})
            await message.reply_text(f"❌ Premium removed from {target}")
        return
    
    premium = await is_premium(user_id)
    if premium:
        user = await premium_col.find_one({"user_id": user_id})
        expiry = user['expiry'].strftime('%Y-%m-%d')
        await message.reply_text(f"✨ Premium Active\n📅 Expires: {expiry}")
    else:
        await message.reply_text("⭐ Free User\n\nUse /upi to buy premium")

@bot.on_message(filters.command("profile"))
async def profile_command(client, message: Message):
    user_id = message.from_user.id
    premium = await is_premium(user_id)
    stats = await stats_col.find_one({"user_id": user_id}) or {}
    
    text = f"""👤 User Profile

ID: {user_id}
Name: {message.from_user.first_name}
Status: {'✨ Premium' if premium else '⭐ Free'}
Total Extractions: {stats.get('total', 0)}
ZIP Downloads: {stats.get('zips', 0)}"""
    
    await message.reply_text(text)

@bot.on_message(filters.command("upi"))
async def upi_command(client, message: Message):
    upi_url = f"upi://pay?pa={UPI_ID}&pn=PremiumBot&am=0&cu=INR"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    qr_path = "/tmp/qr.png"
    img.save(qr_path)
    
    text = f"""💳 Payment Information

UPI ID: {UPI_ID}

Plans:
• 30 Days - ₹99
• 90 Days - ₹249
• 365 Days - ₹799

Pay and forward receipt to @{OWNER_USERNAME}"""
    
    await message.reply_photo(photo=qr_path, caption=text)

# ============ Text Handler ============
@bot.on_message(filters.text & ~filters.command)
async def handle_image_input(client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id not in user_session or not user_session[user_id].get("waiting"):
        await message.reply_text("❌ Use /zip or /files first!")
        return
    
    action = user_session[user_id].get("action")
    image_name = parse_image_name(text)
    user_session[user_id] = {}
    
    status = await message.reply_text(f"🔄 Processing {image_name}...\n⏳ This may take 1-3 minutes")
    
    files_dir, temp_dir, total_files = await docker.extract_image(image_name, status)
    
    if not files_dir:
        await status.edit_text(f"❌ Failed to extract {image_name}\n\nMake sure the image exists.")
        return
    
    if action == "zip":
        await status.edit_text(f"✅ Found {total_files} files!\n📦 Creating ZIP...")
        
        zip_name = image_name.replace('/', '_').replace(':', '_')
        zip_path = f"/tmp/{zip_name}.zip"
        await docker.create_zip(files_dir, zip_path)
        
        zip_size = os.path.getsize(zip_path)
        await status.edit_text(f"📤 Sending ZIP ({total_files} files, {format_size(zip_size)})...")
        
        await message.reply_document(
            document=zip_path,
            caption=f"📦 Image: {image_name}\n📄 Files: {total_files}\n💾 Size: {format_size(zip_size)}",
            file_name=f"{zip_name}.zip"
        )
        
        await docker.cleanup(temp_dir, zip_path)
        await status.delete()
        await update_stats(user_id, "zips")
    
    elif action == "files":
        await status.edit_text(f"✅ Found {total_files} files!\n📝 Sending file list...")
        
        all_files = docker.get_all_files(files_dir)
        
        batch = []
        for f in all_files[:500]:
            batch.append(f"📄 {f['name']} - {format_size(f['size'])}")
            if len(batch) >= 50:
                await message.reply_text("\n".join(batch))
                batch = []
                await asyncio.sleep(0.3)
        
        if batch:
            await message.reply_text("\n".join(batch))
        
        if total_files > 500:
            await message.reply_text(f"⚠️ Showing first 500 of {total_files} files. Use /zip to download all.")
        
        await docker.cleanup(temp_dir)
        await status.delete()

@bot.on_callback_query()
async def callback_handler(client, callback_query):
    if callback_query.data == "buy":
        await upi_command(client, callback_query.message)
    await callback_query.answer()

# ============ Run ============
def run_flask():
    app.run(host="0.0.0.0", port=PORT)

def run_bot():
    bot.run()

if __name__ == "__main__":
    os.makedirs("/tmp/docker_extract", exist_ok=True)
    
    threading.Thread(target=run_flask, daemon=True).start()
    
    print("🤖 Bot starting...")
    bot.run()
