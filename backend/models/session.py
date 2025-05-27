"""
Session model for MongoDB.
"""
from datetime import datetime
from typing import Dict, Any, Optional
from bson import ObjectId

class Session:
    """Session model for MongoDB"""
    
    @staticmethod
    def create(user_id: ObjectId, channel: str, screen_shared: bool, event: str) -> Dict[str, Any]:
        """Create a new session document"""
        return {
            "user_id": user_id,
            "channel": channel,
            "screen_shared": screen_shared,
            "event": event,
            "timestamp": datetime.utcnow()
        }
    
    @staticmethod
    def validate(data: Dict[str, Any]) -> bool:
        """Validate session data"""
        required_fields = ["user_id", "event"]
        valid_events = ["joined", "left", "started_streaming", "stopped_streaming"]
        
        return (
            all(field in data for field in required_fields) and
            data.get("event") in valid_events
        )