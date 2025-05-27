"""
Activity model for MongoDB.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId

class Activity:
    """Activity model for MongoDB"""
    
    @staticmethod
    def create(user_id: ObjectId, active_apps: List[str], active_app: Optional[str], idle_time: int) -> Dict[str, Any]:
        """Create a new activity document"""
        now = datetime.utcnow()
        return {
            "user_id": user_id,
            "active_apps": active_apps,
            "active_app": active_app,
            "idle_time": idle_time,
            "timestamp": now,
            "date": now.date()
        }
    
    @staticmethod
    def validate(data: Dict[str, Any]) -> bool:
        """Validate activity data"""
        required_fields = ["user_id"]
        return all(field in data for field in required_fields)

class AppUsage:
    """App usage model for MongoDB"""
    
    @staticmethod
    def create(user_id: ObjectId, app_name: str) -> Dict[str, Any]:
        """Create a new app usage document"""
        now = datetime.utcnow()
        return {
            "user_id": user_id,
            "app_name": app_name,
            "usage_count": 1,
            "date": now.date(),
            "created_at": now
        }

class DailySummary:
    """Daily summary model for MongoDB"""
    
    @staticmethod
    def create(user_id: ObjectId, date: Optional[datetime] = None) -> Dict[str, Any]:
        """Create a new daily summary document"""
        if date is None:
            date = datetime.utcnow().date()
            
        return {
            "user_id": user_id,
            "date": date,
            "total_screen_share_time": 0,
            "total_active_time": 0,
            "total_idle_time": 0,
            "created_at": datetime.utcnow()
        }