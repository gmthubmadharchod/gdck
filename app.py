import os
import asyncio
import threading
from flask import Flask, request, jsonify, send_file
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db
from docker_handler import DockerExtractor
from utils import generate_qr, format_size
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Pyrogram Bot
bot = Client(
    "premium_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# Docker handler
docker = DockerExtractor()

# Store user data
user_images = {}
user_temp = {}

# ============ Flask Routes ============

@app.route('/')
def home():
    return jsonify({
        "status": "active",
        "bot": "Premium Docker Extractor Bot",
        "version": "2.0",
        "owner": Config.OWNER_ID
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/upi')
def get_upi():
    return jsonify({
        "upi_id": Config.UPI_ID,
        "qr_code": f"/static/qr.png" if os.path.exists("static/qr.png") else None
    })

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_file(f"static/{filename}")

# ============ Telegram Bot Handlers ============

@bot.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id
    is_premium = await db.is_premium(user_id)
    
    text = f"""🔥 **Premium Docker Image Extractor Bot**

Hi {message.from_user.first_name}!

**Features:**
• Extract ANY Docker image
• Get all files with structure
• Fast processing
• Premium benefits

**Commands:**
/start - This message
/image <name> - Set image (e.g., /image ubuntu:latest)
/zip - Download as ZIP
/files - Get file names
/tree - Get folder structure
/premium - Check premium status
/profile - Your profile
/upi - Get payment info

**Your Status:** {'✨ Premium User' if is_premium else '⭐ Free User'}

**Need Premium?** Contact @{Config.OWNER_USERNAME}
"""
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Buy Premium", callback_data="buy_premium")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about")]
    ])
    
    await message.reply_text(text, reply_markup=buttons)

@bot.on_message(filters.command("image"))
async def set_image(client, message: Message):
    user_id = message.from_user.id
    
    if len(message.command) < 2:
        await message.reply_text("❌ Usage: `/image ubuntu:latest`", parse_mode="markdown")
        return
    
    image_name = message.command[1]
    user_images[user_id] = image_name
    
    await message.reply_text(
        f"✅ **Image saved:** `{image_name}`\n\n"
        f"Now use:\n"
        f"`/zip` - Download complete repository\n"
        f"`/files` - Get all file names\n"
        f"`/tree` - Get folder structure",
        parse_mode="markdown"
    )

@bot.on_message(filters.command("zip"))
async def zip_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_images:
        await message.reply_text("❌ First set image using `/image ubuntu:latest`", parse_mode="markdown")
        return
    
    image_name = user_images[user_id]
    is_premium = await db.is_premium(user_id)
    
    status_msg = await message.reply_text(f"🔄 Extracting `{image_name}`...\n⏳ Please wait 1-3 minutes", parse_mode="markdown")
    
    # Extract
    result = await docker.extract_image(image_name, status_msg)
    
    if not result:
        await status_msg.edit_text(f"❌ Failed to extract `{image_name}`. Check if image exists!")
        return
    
    files_dir, temp_dir, total_files = result
    
    await status_msg.edit_text(f"✅ {total_files} files extracted!\n📦 Creating ZIP...")
    
    # Create ZIP
    zip_name = image_name.replace('/', '_').replace(':', '_')
    zip_path = f"{Config.TEMP_DIR}/{zip_name}.zip"
    
    await docker.create_zip(files_dir, zip_path)
    
    await status_msg.edit_text(f"📤 Sending ZIP ({total_files} files)...")
    
    # Send ZIP
    await message.reply_document(
        document=zip_path,
        caption=f"📦 **Image:** `{image_name}`\n📄 **Files:** {total_files}\n💎 **Status:** {'Premium' if is_premium else 'Free'}",
        file_name=f"{zip_name}.zip"
    )
    
    # Cleanup
    await docker.cleanup(temp_dir, zip_path)
    await status_msg.delete()

@bot.on_message(filters.command("files"))
async def files_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_images:
        await message.reply_text("❌ First set image using `/image ubuntu:latest`", parse_mode="markdown")
        return
    
    image_name = user_images[user_id]
    status_msg = await message.reply_text(f"🔄 Extracting `{image_name}`...", parse_mode="markdown")
    
    result = await docker.extract_image(image_name, status_msg)
    
    if not result:
        await status_msg.edit_text(f"❌ Failed!")
        return
    
    files_dir, temp_dir, total_files = result
    
    await status_msg.edit_text(f"✅ {total_files} files found!\n📝 Sending file list...")
    
    # Get all files
    all_files = docker.get_all_files(files_dir)
    
    # Send in batches
    batch = []
    for i, file_info in enumerate(all_files[:500], 1):
        batch.append(f"📄 `{file_info['name']}` - {format_size(file_info['size'])}")
        
        if len(batch) >= 50:
            await message.reply_text("\n".join(batch))
            batch = []
            await asyncio.sleep(0.3)
    
    if batch:
        await message.reply_text("\n".join(batch))
    
    if total_files > 500:
        await message.reply_text(f"⚠️ Showing first 500 of {total_files} files. Use `/zip` to download all.")
    
    await docker.cleanup(temp_dir)
    await status_msg.delete()

@bot.on_message(filters.command("tree"))
async def tree_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_images:
        await message.reply_text("❌ First set image using `/image ubuntu:latest`", parse_mode="markdown")
        return
    
    image_name = user_images[user_id]
    status_msg = await message.reply_text(f"🔄 Analyzing `{image_name}`...", parse_mode="markdown")
    
    result = await docker.extract_image(image_name, status_msg)
    
    if not result:
        await status_msg.edit_text(f"❌ Failed!")
        return
    
    files_dir, temp_dir, total_files = result
    
    tree_text = await docker.get_folder_tree(files_dir, total_files)
    
    await message.reply_text(tree_text, parse_mode="markdown")
    await docker.cleanup(temp_dir)
    await status_msg.delete()

@bot.on_message(filters.command("premium"))
async def premium_command(client, message: Message):
    user_id = message.from_user.id
    
    # Owner commands
    if user_id == Config.OWNER_ID and len(message.command) > 2:
        action = message.command[1]
        target_id = int(message.command[2])
        
        if action == "add":
            days = int(message.command[3]) if len(message.command) > 3 else 30
            await db.add_premium(target_id, days)
            await message.reply_text(f"✅ Premium added to `{target_id}` for {days} days!")
        elif action == "remove":
            await db.remove_premium(target_id)
            await message.reply_text(f"❌ Premium removed from `{target_id}`")
        elif action == "list":
            users = await db.get_all_premium()
            text = "📋 **Premium Users:**\n\n"
            for u in users:
                text += f"• `{u['user_id']}` - Expires: {u['expiry'].strftime('%Y-%m-%d')}\n"
            await message.reply_text(text)
        return
    
    # User check
    is_premium = await db.is_premium(user_id)
    
    if is_premium:
        user_data = await db.get_user(user_id)
        expiry = user_data['expiry'].strftime('%Y-%m-%d %H:%M:%S')
        await message.reply_text(
            f"✨ **Premium Status:** Active\n"
            f"📅 **Expires:** {expiry}\n"
            f"🎁 **Features:** Unlimited extractions, priority processing",
            parse_mode="markdown"
        )
    else:
        await message.reply_text(
            "⭐ **Free User**\n\n"
            "**Premium Benefits:**\n"
            "• Unlimited extractions\n"
            "• Priority queue\n"
            "• Larger file support\n"
            "• Direct support\n\n"
            f"💳 **Buy Premium:** /upi",
            parse_mode="markdown"
        )

@bot.on_message(filters.command("profile"))
async def profile_command(client, message: Message):
    user_id = message.from_user.id
    is_premium = await db.is_premium(user_id)
    
    stats = await db.get_user_stats(user_id)
    
    text = f"""👤 **User Profile**

**ID:** `{user_id}`
**Name:** {message.from_user.first_name}
**Status:** {'✨ Premium' if is_premium else '⭐ Free'}
**Total Extractions:** {stats.get('total', 0)}
**Total ZIPs:** {stats.get('zips', 0)}

Use /premium for more details"""
    
    await message.reply_text(text, parse_mode="markdown")

@bot.on_message(filters.command("upi"))
async def upi_command(client, message: Message):
    # Generate fresh QR
    qr_path = await generate_qr(Config.UPI_ID)
    
    text = f"""💳 **Payment Information**

**UPI ID:** `{Config.UPI_ID}`

**Plans:**
• 30 Days - ₹99
• 90 Days - ₹249
• 365 Days - ₹799

**How to Pay:**
1. Scan QR code
2. Send payment
3. Forward receipt to @{Config.OWNER_USERNAME}

**QR Code:** (attached below)"""
    
    if qr_path and os.path.exists(qr_path):
        await message.reply_photo(photo=qr_path, caption=text, parse_mode="markdown")
    else:
        await message.reply_text(text, parse_mode="markdown")

@bot.on_message(filters.command("set_upi"))
async def set_upi_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id != Config.OWNER_ID:
        await message.reply_text("❌ Owner only command!")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: `/set_upi your_upi@ybl`", parse_mode="markdown")
        return
    
    new_upi = message.command[1]
    
    # Update config (optional: save to file/db)
    Config.UPI_ID = new_upi
    
    # Generate new QR
    await generate_qr(new_upi)
    
    await message.reply_text(f"✅ UPI ID updated to: `{new_upi}`\n🔄 QR code regenerated!", parse_mode="markdown")

@bot.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    
    if data == "buy_premium":
        await upi_command(client, callback_query.message)
        await callback_query.answer()
    
    elif data == "about":
        text = """🤖 **About Bot**

**Version:** 2.0 Premium
**Framework:** Pyrogram + Flask
**Features:**
• Docker image extraction
• Full file system access
• Premium user system
• MongoDB database

**Owner:** @owner_username
**Support:** @support_group"""
        
        await callback_query.message.reply_text(text)
        await callback_query.answer()

# ============ Run Both ============

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def run_bot():
    bot.run()

if __name__ == "__main__":
    # Create static folder
    os.makedirs("static", exist_ok=True)
    os.makedirs(Config.TEMP_DIR, exist_ok=True)
    
    # Connect to MongoDB
    asyncio.get_event_loop().run_until_complete(db.connect())
    
    # Start both
    threading.Thread(target=run_flask).start()
    run_bot()
