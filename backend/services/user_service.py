"""
User service for handling user-related operations.
"""
import logging
from datetime import datetime
from bson import ObjectId
from mongodb import users_collection, sessions_collection

logger = logging.getLogger(__name__)

class UserService:
    """Service for handling user-related operations"""
    
    def get_or_create_user(self, username):
        """Get user by username or create if not exists"""
        user = users_collection.find_one({"username": username})
        
        if user:
            return user["_id"]
        
        # Create new user
        result = users_collection.insert_one({
            "username": username,
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow(),
            "is_active": True
        })
        
        logger.info(f"✅ Created new user: {username}")
        return result.inserted_id
    
    def update_user(self, user_id, update_data):
        """Update user information"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        result = users_collection.update_one(
            {"_id": user_id},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        return users_collection.find_one({"_id": user_id})
    
    def get_user_by_username(self, username):
        """Get user by username"""
        return users_collection.find_one({"username": username})
    
    def get_all_users(self):
        """Get all users"""
        return list(users_collection.find())
    
    def get_users_paginated(self, skip=0, limit=100):
        """Get users with pagination"""
        return list(users_collection.find().skip(skip).limit(limit))
    
    def get_user_count(self):
        """Get total number of users"""
        return users_collection.count_documents({})
    
    def get_active_users(self):
        """Get all active users"""
        return list(users_collection.find({"is_active": True}))
    
    def update_user_activity(self, user_id):
        """Update user's last active timestamp"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        users_collection.update_one(
            {"_id": user_id},
            {"$set": {"last_active": datetime.utcnow()}}
        )
    
    def get_user_session_status(self, user_id):
        """Get user's current session status"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        # Get the most recent session for this user
        latest_session = sessions_collection.find_one(
            {"user_id": user_id},
            sort=[("timestamp", -1)]
        )
        
        if not latest_session:
            return "offline"
        
        # Check if the user is in a meeting
        if latest_session.get("event") == "joined":
            return "in_meeting"
        elif latest_session.get("event") == "started_streaming":
            return "streaming"
        
        return "online"

# Create a singleton instance
user_service = UserService()