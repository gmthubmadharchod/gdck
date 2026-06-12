import os

class Config:
    # Telegram
    API_ID = int(os.getenv("API_ID", "123456"))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    
    # MongoDB
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "premium_bot")
    
    # Owner
    OWNER_ID = int(os.getenv("OWNER_ID", "0"))
    OWNER_USERNAME = os.getenv("OWNER_USERNAME", "owner_username")
    
    # Payment
    UPI_ID = os.getenv("UPI_ID", "owner@ybl")
    
    # Bot Settings
    TEMP_DIR = "/tmp/docker_extract"
    
    @classmethod
    def validate(cls):
        required = ["API_ID", "API_HASH", "BOT_TOKEN", "MONGO_URL", "OWNER_ID"]
        missing = [r for r in required if not os.getenv(r)]
        if missing:
            raise ValueError(f"Missing env vars: {missing}")
