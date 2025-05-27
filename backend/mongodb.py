from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import os
import time
import logging
from typing import Optional
import pymongo  # Added for error handling

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MongoDBConnection:
    _instance: Optional['MongoDBConnection'] = None
    _client: Optional[MongoClient] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBConnection, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.connect()
    
    def connect(self, max_retries: int = 3, retry_delay: int = 5):
        """Establish connection to MongoDB with retry mechanism"""
        MONGO_URI = os.getenv("MONGO_URI", "mongodb://db:27017")
        
        for attempt in range(max_retries):
            try:
                self._client = MongoClient(
                    MONGO_URI,
                    serverSelectionTimeoutMS=5000,
                    maxPoolSize=50,
                    minPoolSize=10,
                    maxIdleTimeMS=30000,
                    waitQueueTimeoutMS=10000
                )
                # Test the connection
                self._client.admin.command('ping')
                logger.info("Successfully connected to MongoDB")
                break
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                if attempt == max_retries - 1:
                    # Use %s for string formatting to prevent log injection
                    logger.error("Failed to connect to MongoDB after %s attempts: %s", max_retries, str(e))
                    raise
                logger.warning(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
    
    @property
    def client(self) -> MongoClient:
        """Get MongoDB client instance"""
        if self._client is None:
            self.connect()
        return self._client
    
    def get_database(self, db_name: str = "wfh_monitoring"):
        """Get database instance"""
        return self.client[db_name]

# Initialize MongoDB connection
mongo_connection = MongoDBConnection()
db = mongo_connection.get_database()

# Collections
users_collection = db["users"]
sessions_collection = db["sessions"]
activities_collection = db["activities"]
daily_summaries_collection = db["daily_summaries"]
app_usage_collection = db["app_usage"]

# Create indexes for better query performance
def create_indexes():
    try:
        # Users collection indexes
        users_collection.create_index("username", unique=True)
        users_collection.create_index("display_name")  # Add index for display_name
        
        # Sessions collection indexes
        sessions_collection.create_index([("user_id", 1), ("timestamp", -1)])
        sessions_collection.create_index("screen_shared")
        
        # Activities collection indexes
        activities_collection.create_index([("user_id", 1), ("date", 1)])
        activities_collection.create_index([("user_id", 1), ("app_name", 1), ("date", 1)])
        
        # Daily summaries collection indexes
        daily_summaries_collection.create_index([("user_id", 1), ("date", 1)])
        
        logger.info("Successfully created database indexes")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")

# Create indexes on startup
create_indexes()