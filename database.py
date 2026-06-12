from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from config import Config

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.users = None
        self.premium = None
        self.stats = None
    
    async def connect(self):
        self.client = AsyncIOMotorClient(Config.MONGO_URL)
        self.db = self.client[Config.DATABASE_NAME]
        self.users = self.db["users"]
        self.premium = self.db["premium_users"]
        self.stats = self.db["user_stats"]
        
        # Indexes
        await self.premium.create_index("user_id", unique=True)
        await self.users.create_index("user_id", unique=True)
    
    async def add_premium(self, user_id, days=30):
        expiry = datetime.now() + timedelta(days=days)
        await self.premium.update_one(
            {"user_id": user_id},
            {"$set": {"expiry": expiry, "active": True, "added_on": datetime.now()}},
            upsert=True
        )
        return True
    
    async def remove_premium(self, user_id):
        await self.premium.delete_one({"user_id": user_id})
        return True
    
    async def is_premium(self, user_id):
        user = await self.premium.find_one({"user_id": user_id})
        if user and user.get("active"):
            if user["expiry"] > datetime.now():
                return True
            else:
                await self.premium.update_one(
                    {"user_id": user_id},
                    {"$set": {"active": False}}
                )
        return False
    
    async def get_user(self, user_id):
        return await self.premium.find_one({"user_id": user_id})
    
    async def get_all_premium(self):
        cursor = self.premium.find({"active": True})
        return await cursor.to_list(length=None)
    
    async def update_stats(self, user_id, action):
        await self.stats.update_one(
            {"user_id": user_id},
            {"$inc": {f"{action}": 1, "total": 1}},
            upsert=True
        )
    
    async def get_user_stats(self, user_id):
        stats = await self.stats.find_one({"user_id": user_id})
        return stats or {"total": 0, "zips": 0, "files": 0}

db = Database()
