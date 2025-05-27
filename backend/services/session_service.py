"""
Session service for handling session-related operations.
"""
import logging
from datetime import datetime
from bson import ObjectId
from mongodb import sessions_collection, daily_summaries_collection

logger = logging.getLogger(__name__)

class SessionService:
    """Service for handling session-related operations"""
    
    def create_session(self, user_id, data):
        """Create a new session record"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        session_data = {
            "user_id": user_id,
            "channel": data.get("channel"),
            "screen_shared": data.get("screen_shared", False),
            "event": data.get("event"),
            "timestamp": datetime.utcnow()
        }
        
        result = sessions_collection.insert_one(session_data)
        logger.info(f"✅ Created new session for user {user_id}")
        
        return result.inserted_id
    
    def get_user_sessions(self, user_id, limit=100):
        """Get sessions for a specific user"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        return list(sessions_collection.find(
            {"user_id": user_id},
            sort=[("timestamp", -1)],
            limit=limit
        ))
    
    def get_recent_sessions(self, limit=100):
        """Get recent sessions across all users"""
        return list(sessions_collection.find(
            sort=[("timestamp", -1)],
            limit=limit
        ))
    
    def handle_session_event(self, user_id, data):
        """Handle session event (join, leave, start/stop streaming)"""
        event = data.get("event")
        
        if event == "joined":
            self._handle_join_event(user_id, data)
        elif event == "left":
            self._handle_leave_event(user_id, data)
        elif event == "started_streaming":
            self._handle_start_streaming_event(user_id, data)
        elif event == "stopped_streaming":
            self._handle_stop_streaming_event(user_id, data)
    
    def _handle_join_event(self, user_id, data):
        """Handle join meeting event"""
        self.create_session(user_id, data)
    
    def _handle_leave_event(self, user_id, data):
        """Handle leave meeting event"""
        self.create_session(user_id, data)
    
    def _handle_start_streaming_event(self, user_id, data):
        """Handle start streaming event"""
        data["screen_shared"] = True
        self.create_session(user_id, data)
    
    def _handle_stop_streaming_event(self, user_id, data):
        """Handle stop streaming event"""
        data["screen_shared"] = False
        self.create_session(user_id, data)
        
        # Calculate streaming duration and update daily summary
        self._update_streaming_time(user_id)
    
    def _update_streaming_time(self, user_id):
        """Calculate streaming time and update daily summary"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        # Find the most recent stop_streaming event
        stop_event = sessions_collection.find_one(
            {"user_id": user_id, "event": "stopped_streaming"},
            sort=[("timestamp", -1)]
        )
        
        if not stop_event:
            return
        
        # Find the matching start_streaming event
        start_event = sessions_collection.find_one(
            {
                "user_id": user_id,
                "event": "started_streaming",
                "timestamp": {"$lt": stop_event["timestamp"]}
            },
            sort=[("timestamp", -1)]
        )
        
        if not start_event:
            return
        
        # Calculate streaming duration in seconds
        duration = (stop_event["timestamp"] - start_event["timestamp"]).total_seconds()
        
        # Update daily summary
        today = datetime.utcnow().date()
        
        daily_summaries_collection.update_one(
            {"user_id": user_id, "date": today},
            {
                "$inc": {"total_screen_share_time": duration},
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
        
        logger.info(f"✅ Updated streaming time for user {user_id}: {duration} seconds")

# Create a singleton instance
session_service = SessionService()