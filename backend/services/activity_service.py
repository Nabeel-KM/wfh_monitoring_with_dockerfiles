"""
Activity service for handling activity-related operations.
"""
import logging
from datetime import datetime
from bson import ObjectId
from mongodb import activities_collection, app_usage_collection, daily_summaries_collection

logger = logging.getLogger(__name__)

class ActivityService:
    """Service for handling activity-related operations"""
    
    def record_activity(self, user_id, data):
        """Record user activity"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        activity_data = {
            "user_id": user_id,
            "active_apps": data.get("active_apps", []),
            "active_app": data.get("active_app"),
            "idle_time": data.get("idle_time", 0),
            "timestamp": datetime.utcnow(),
            "date": datetime.utcnow().date()
        }
        
        result = activities_collection.insert_one(activity_data)
        
        # Update app usage statistics
        self._update_app_usage(user_id, data.get("active_app"))
        
        return result.inserted_id
    
    def _update_app_usage(self, user_id, app_name):
        """Update app usage statistics"""
        if not app_name:
            return
            
        today = datetime.utcnow().date()
        
        app_usage_collection.update_one(
            {
                "user_id": user_id,
                "app_name": app_name,
                "date": today
            },
            {
                "$inc": {"usage_count": 1},
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
    
    def get_user_activities(self, user_id, start_date=None, end_date=None, limit=100):
        """Get activities for a specific user within a date range"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        query = {"user_id": user_id}
        
        if start_date:
            if not end_date:
                end_date = datetime.utcnow().date()
            query["date"] = {"$gte": start_date, "$lte": end_date}
            
        return list(activities_collection.find(
            query,
            sort=[("timestamp", -1)],
            limit=limit
        ))
    
    def get_app_usage(self, user_id, date=None):
        """Get app usage statistics for a user"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        query = {"user_id": user_id}
        
        if date:
            query["date"] = date
            
        return list(app_usage_collection.find(
            query,
            sort=[("usage_count", -1)]
        ))
    
    def get_daily_summary(self, user_id, date=None):
        """Get daily summary for a user"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        if not date:
            date = datetime.utcnow().date()
            
        return daily_summaries_collection.find_one({
            "user_id": user_id,
            "date": date
        })
    
    def update_daily_summary(self, user_id, data):
        """Update daily summary for a user"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        today = datetime.utcnow().date()
        
        daily_summaries_collection.update_one(
            {"user_id": user_id, "date": today},
            {
                "$set": data,
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )

# Create a singleton instance
activity_service = ActivityService()