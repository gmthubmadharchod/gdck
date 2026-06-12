import os
import subprocess
import shutil
import zipfile
import asyncio
import threading
import re
from flask import Flask, request, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import qrcode

# ============ CONFIG ============
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
OWNER_ID = int(os.getenv("OWNER_ID"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "owner")
UPI_ID = os.getenv("UPI_ID", "owner@ybl")
PORT = int(os.getenv("PORT", 8080))
TEMP_DIR = "/tmp/docker_extract"
# ================================

app = Flask(__name__)

# MongoDB
client_mongo = AsyncIOMotorClient(MONGO_URL)
db = client_mongo["premium_bot"]
premium_col = db["premium_users"]
stats_col = db["user_stats"]
sessions_col = db["sessions"]

# Pyrogram Bot
bot = Client("premium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Store user session state
user_state = {}  # {user_id: {"step": "waiting_for_image", "image": None}}

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

# ============ Docker Extraction ============
async def extract_docker_image(image_name, status_msg=None):
    safe_name = image_name.replace('/', '_').replace(':', '_')
    temp_dir = f"{TEMP_DIR}/{safe_name}"
    
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        if status_msg:
            await status_msg.edit_text(f"🔄 Pulling {image_name}...")
        
        proc = await asyncio.create_subprocess_shell(
            f"docker pull {image_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        if status_msg:
            await status_msg.edit_text(f"📦 Creating container...")
        
        proc = await asyncio.create_subprocess_shell(
            f"docker create {image_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            text=True
        )
        stdout, _ = await proc.communicate()
        container_id = stdout.strip()
        
        if status_msg:
            await status_msg.edit_text(f"📂 Exporting filesystem...")
        
        export_tar = f"{temp_dir}/export.tar"
        await asyncio.create_subprocess_shell(
            f"docker export {container_id} -o {export_tar}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        if status_msg:
            await status_msg.edit_text(f"📁 Extracting files...")
        
        files_dir = f"{temp_dir}/files"
        os.makedirs(files_dir, exist_ok=True)
        await asyncio.create_subprocess_shell(
            f"tar -xf {export_tar} -C {files_dir} 2>/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await asyncio.create_subprocess_shell(f"docker rm {container_id}")
        
        total = 0
        for _, _, files in os.walk(files_dir):
            total += len(files)
        
        return files_dir, temp_dir, total
        
    except Exception as e:
        print(f"Extract error: {e}")
        return None, None, 0

def get_all_files(directory):
    files = []
    for root, _, filenames in os.walk(directory):
        for f in filenames:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, directory)
            size = os.path.getsize(full)
            files.append({"name": rel, "size": size, "path": full})
    return files

async def create_zip(source_dir, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)

# ============ Flask Routes ============
@app.route('/')
def home():
    return jsonify({"status": "active", "bot": "Docker Extractor Bot"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

# ============ Telegram Bot Commands ============

@bot.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id
    premium = await is_premium(user_id)
    
    # Reset user state
    user_state[user_id] = {"step": None, "image": None}
    
    text = f"""🔥 <b>Docker Image Extractor Bot</b>

Hi {message.from_user.first_name}!

<b>How to use:</b>
1️⃣ Send /extract command
2️⃣ Bot will ask for image name/URL
3️⃣ Send image (like: ubuntu:latest)
4️⃣ Then use /zip or /files

<b>Commands:</b>
/extract - Start extraction process
/zip - Download as ZIP
/files - Get file list
/tree - Show folder structure
/premium - Check status
/upi - Payment info
/profile - Your stats

<b>Status:</b> {'✨ Premium' if premium else '⭐ Free'}"""
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Extraction", callback_data="start_extract")],
        [InlineKeyboardButton("📦 Buy Premium", callback_data="buy")]
    ])
    
    await message.reply_text(text, reply_markup=buttons)

@bot.on_message(filters.command("extract"))
async def extract_command(client, message: Message):
    user_id = message.from_user.id
    
    # Set state to waiting for image
    user_state[user_id] = {"step": "waiting_for_image", "image": None}
    
    text = """🔍 <b>Send me the Docker image</b>

<b>Examples:</b>
• <code>ubuntu:latest</code>
• <code>nginx:alpine</code>
• <code>python:3.9</code>
• <code>library/redis</code>

<b>Or Docker Hub URL:</b>
• <code>https://hub.docker.com/r/library/ubuntu</code>

<i>Send the image name/URL now...</i>"""
    
    await message.reply_text(text, parse_mode="HTML")

@bot.on_message(filters.command("cancel"))
async def cancel_command(client, message: Message):
    user_id = message.from_user.id
    if user_id in user_state:
        user_state[user_id] = {"step": None, "image": None}
    await message.reply_text("✅ Cancelled. Use /extract to start again.")

@bot.on_message(filters.text & ~filters.command)
async def handle_text_input(client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Check if waiting for image
    if user_id in user_state and user_state[user_id].get("step") == "waiting_for_image":
        # Parse image name
        image_name = parse_image_name(text)
        user_state[user_id]["image"] = image_name
        user_state[user_id]["step"] = "image_ready"
        
        await message.reply_text(
            f"✅ <b>Image saved:</b> <code>{image_name}</code>\n\n"
            f"Now use these commands:\n"
            f"• /zip - Download all files as ZIP\n"
            f"• /files - Get list of all files\n"
            f"• /tree - Show folder structure\n\n"
            f"<i>Or send /extract again for new image</i>",
            parse_mode="HTML"
        )
        return
    
    # If not waiting, ignore or show help
    await message.reply_text(
        "❌ Use /extract first to set an image!",
        parse_mode="HTML"
    )

@bot.on_message(filters.command("zip"))
async def zip_command(client, message: Message):
    user_id = message.from_user.id
    
    # Check if image is set
    if user_id not in user_state or not user_state[user_id].get("image"):
        await message.reply_text(
            "❌ No image set!\n\nUse /extract first to set a Docker image.",
            parse_mode="HTML"
        )
        return
    
    image_name = user_state[user_id]["image"]
    status = await message.reply_text(f"🔄 Processing <code>{image_name}</code>...\n⏳ This may take 1-3 minutes", parse_mode="HTML")
    
    # Extract
    files_dir, temp_dir, total = await extract_docker_image(image_name, status)
    
    if not files_dir:
        await status.edit_text(f"❌ Failed to extract <code>{image_name}</code>\n\nMake sure the image exists.", parse_mode="HTML")
        return
    
    await status.edit_text(f"✅ Found {total} files!\n📦 Creating ZIP...")
    
    # Create ZIP
    zip_name = image_name.replace('/', '_').replace(':', '_')
    zip_path = f"{TEMP_DIR}/{zip_name}.zip"
    await create_zip(files_dir, zip_path)
    
    zip_size = os.path.getsize(zip_path)
    await status.edit_text(f"📤 Sending ZIP ({total} files, {format_size(zip_size)})...")
    
    # Send ZIP
    await message.reply_document(
        document=zip_path,
        caption=f"📦 <b>Image:</b> <code>{image_name}</code>\n📄 <b>Files:</b> {total}\n💾 <b>Size:</b> {format_size(zip_size)}",
        file_name=f"{zip_name}.zip",
        parse_mode="HTML"
    )
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    await status.delete()
    
    await update_stats(user_id, "zips")

@bot.on_message(filters.command("files"))
async def files_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_state or not user_state[user_id].get("image"):
        await message.reply_text(
            "❌ No image set!\n\nUse /extract first to set a Docker image.",
            parse_mode="HTML"
        )
        return
    
    image_name = user_state[user_id]["image"]
    status = await message.reply_text(f"🔄 Processing <code>{image_name}</code>...", parse_mode="HTML")
    
    files_dir, temp_dir, total = await extract_docker_image(image_name, status)
    
    if not files_dir:
        await status.edit_text(f"❌ Failed to extract <code>{image_name}</code>", parse_mode="HTML")
        return
    
    all_files = get_all_files(files_dir)
    
    await status.edit_text(f"✅ Found {total} files!\n📝 Sending file list...")
    
    # Send in batches
    batch = []
    for i, f in enumerate(all_files[:500], 1):
        batch.append(f"📄 <code>{f['name']}</code> - {format_size(f['size'])}")
        
        if len(batch) >= 50:
            await message.reply_text("\n".join(batch), parse_mode="HTML")
            batch = []
            await asyncio.sleep(0.3)
    
    if batch:
        await message.reply_text("\n".join(batch), parse_mode="HTML")
    
    if total > 500:
        await message.reply_text(f"⚠️ Showing first 500 of {total} files. Use /zip to download all.", parse_mode="HTML")
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    await status.delete()

@bot.on_message(filters.command("tree"))
async def tree_command(client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_state or not user_state[user_id].get("image"):
        await message.reply_text(
            "❌ No image set!\n\nUse /extract first to set a Docker image.",
            parse_mode="HTML"
        )
        return
    
    image_name = user_state[user_id]["image"]
    status = await message.reply_text(f"🔄 Analyzing <code>{image_name}</code>...", parse_mode="HTML")
    
    files_dir, temp_dir, total = await extract_docker_image(image_name, status)
    
    if not files_dir:
        await status.edit_text(f"❌ Failed!", parse_mode="HTML")
        return
    
    # Build tree
    tree_lines = ["📁 <b>Folder Structure</b>\n"]
    
    def build_tree(path="", prefix=""):
        lines = []
        items = []
        
        full_path = os.path.join(files_dir, path) if path else files_dir
        if os.path.exists(full_path):
            for item in sorted(os.listdir(full_path)):
                items.append(item)
        
        for i, item in enumerate(items):
            item_path = os.path.join(path, item) if path else item
            full_item = os.path.join(files_dir, item_path)
            is_last = (i == len(items) - 1)
            
            if os.path.isdir(full_item):
                lines.append(f"{prefix}{'└── ' if is_last else '├── '}📁 {item}/")
                lines.extend(build_tree(item_path, prefix + ('    ' if is_last else '│   ')))
            else:
                size = os.path.getsize(full_item)
                lines.append(f"{prefix}{'└── ' if is_last else '├── '}📄 {item} ({format_size(size)})")
        
        return lines
    
    tree_lines.extend(build_tree())
    tree_lines.append(f"\n📊 <b>Total:</b> {total} files")
    
    tree_text = "\n".join(tree_lines)
    if len(tree_text) > 4000:
        tree_text = tree_text[:4000] + "\n\n... (truncated)"
    
    await message.reply_text(tree_text, parse_mode="HTML")
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    await status.delete()

@bot.on_message(filters.command("premium"))
async def premium_command(client, message: Message):
    user_id = message.from_user.id
    
    # Owner commands
    if user_id == OWNER_ID and len(message.command) > 2:
        action = message.command[1]
        target = int(message.command[2])
        
        if action == "add":
            days = int(message.command[3]) if len(message.command) > 3 else 30
            await add_premium(target, days)
            await message.reply_text(f"✅ Premium added to <code>{target}</code> for {days} days!", parse_mode="HTML")
        elif action == "remove":
            await premium_col.delete_one({"user_id": target})
            await message.reply_text(f"❌ Premium removed from <code>{target}</code>", parse_mode="HTML")
        return
    
    premium = await is_premium(user_id)
    if premium:
        user = await premium_col.find_one({"user_id": user_id})
        expiry = user['expiry'].strftime('%Y-%m-%d')
        await message.reply_text(f"✨ <b>Premium Active</b>\n📅 Expires: {expiry}", parse_mode="HTML")
    else:
        await message.reply_text(
            "⭐ <b>Free User</b>\n\n"
            "<b>Premium Benefits:</b>\n"
            "• Unlimited extractions\n"
            "• Priority processing\n"
            "• Larger file support\n\n"
            "Use /upi to buy premium",
            parse_mode="HTML"
        )

@bot.on_message(filters.command("profile"))
async def profile_command(client, message: Message):
    user_id = message.from_user.id
    premium = await is_premium(user_id)
    stats = await stats_col.find_one({"user_id": user_id}) or {}
    
    text = f"""<b>👤 User Profile</b>

<b>ID:</b> <code>{user_id}</code>
<b>Name:</b> {message.from_user.first_name}
<b>Status:</b> {'✨ Premium' if premium else '⭐ Free'}
<b>Total Extractions:</b> {stats.get('total', 0)}
<b>ZIP Downloads:</b> {stats.get('zips', 0)}"""
    
    await message.reply_text(text, parse_mode="HTML")

@bot.on_message(filters.command("upi"))
async def upi_command(client, message: Message):
    # Generate QR
    upi_url = f"upi://pay?pa={UPI_ID}&pn=PremiumBot&am=0&cu=INR"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    qr_path = "/tmp/qr.png"
    img.save(qr_path)
    
    text = f"""<b>💳 Payment Information</b>

<b>UPI ID:</b> <code>{UPI_ID}</code>

<b>Plans:</b>
• 30 Days - ₹99
• 90 Days - ₹249
• 365 Days - ₹799

<b>How to Pay:</b>
1. Scan QR code below
2. Send payment
3. Forward receipt to @{OWNER_USERNAME}

<i>You will be activated within 24 hours</i>"""
    
    await message.reply_photo(photo=qr_path, caption=text, parse_mode="HTML")

@bot.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    
    if data == "start_extract":
        # Trigger extract command
        await extract_command(client, callback_query.message)
    elif data == "buy":
        await upi_command(client, callback_query.message)
    
    await callback_query.answer()

def parse_image_name(text):
    """Parse image name from various inputs"""
    text = text.strip()
    
    # Check if it's a Docker Hub URL
    url_pattern = r'https?://hub\.docker\.com/r/([^/]+)/([^/]+)'
    match = re.match(url_pattern, text)
    if match:
        return f"{match.group(1)}/{match.group(2)}:latest"
    
    # Check if it's username/repo:tag format
    if '/' in text or ':' in text:
        return text
    
    # Default to library/image
    return f"library/{text}:latest"

# ============ Run ============
def run_flask():
    app.run(host="0.0.0.0", port=PORT)

def run_bot():
    bot.run()

if __name__ == "__main__":
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # Start Flask in background
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Run bot
    print("🤖 Bot starting...")
    bot.run()
