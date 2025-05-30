from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection settings
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'wfh_monitoring')

# Global variables for database and collections
client: Optional[AsyncIOMotorClient] = None
db = None
users_collection = None
sessions_collection = None
activities_collection = None
daily_summaries_collection = None

async def connect_to_mongodb():
    """Create database connection."""
    global client, db, users_collection, sessions_collection, activities_collection, daily_summaries_collection
    
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client[DATABASE_NAME]
        
        # Initialize collections
        users_collection = db.users
        sessions_collection = db.sessions
        activities_collection = db.activities
        daily_summaries_collection = db.daily_summaries
        
        # Create indexes
        await users_collection.create_index("username", unique=True)
        await sessions_collection.create_index([("user_id", 1), ("timestamp", -1)])
        await sessions_collection.create_index([("user_id", 1), ("start_time", 1)])
        await sessions_collection.create_index([("user_id", 1), ("stop_time", -1)])
        await activities_collection.create_index([("user_id", 1), ("date", 1), ("app_name", 1)])
        await daily_summaries_collection.create_index([("user_id", 1), ("date", 1)])
        
        return True
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return False

async def close_mongodb_connection():
    """Close database connection."""
    global client
    if client:
        client.close()

def get_database():
    """Get database instance."""
    return db

def get_collections():
    """Get all collections."""
    return {
        "users": users_collection,
        "sessions": sessions_collection,
        "activities": activities_collection,
        "daily_summaries": daily_summaries_collection
    } 