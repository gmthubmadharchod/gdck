import qrcode
import os
from datetime import datetime

async def generate_qr(upi_id):
    """Generate QR code for UPI payment"""
    upi_url = f"upi://pay?pa={upi_id}&pn=PremiumBot&am=0&cu=INR"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to static folder
    os.makedirs("static", exist_ok=True)
    qr_path = f"static/qr_{datetime.now().strftime('%Y%m%d')}.png"
    img.save(qr_path)
    
    # Also save as latest
    latest_path = "static/qr.png"
    img.save(latest_path)
    
    return latest_path

def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024*1024:
        return f"{size/1024:.2f} KB"
    elif size < 1024*1024*1024:
        return f"{size/(1024*1024):.2f} MB"
    else:
        return f"{size/(1024*1024*1024):.2f} GB"

async def update_config(key, value):
    """Update config dynamically (for owner)"""
    # This can be extended to save to file/db
    os.environ[key] = value
    return True
