"""
Service for managing user sessions
"""
import logging
from datetime import datetime, timezone
from bson import ObjectId
from mongodb import sessions_collection, daily_summaries_collection
from utils.helpers import ensure_timezone_aware, logger

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
    
    def calculate_session_time(self, first_join, last_leave):
        """Calculate total session time in hours"""
        if not (first_join and last_leave and 
                first_join.get("start_time") and 
                last_leave.get("stop_time")):
            return 0
        
        try:
            first_join_time = ensure_timezone_aware(first_join["start_time"])
            last_leave_time = ensure_timezone_aware(last_leave["stop_time"])
            
            if last_leave_time > first_join_time:
                total_seconds = (last_leave_time - first_join_time).total_seconds()
                hours = round(total_seconds / 3600, 2)
                logger.info(f"Session time calculated: {hours} hours")
                return hours
            else:
                logger.warning(f"Invalid session times: {first_join_time} -> {last_leave_time}")
                return 0
        except Exception as e:
            logger.error(f"Error calculating session time: {e}", exc_info=True)
            return 0

    def get_session_data(self, user_id, date):
        """Get session data for user on date"""
        try:
            day_start = datetime.combine(date, datetime.min.time(), tzinfo=timezone.utc)
            day_end = datetime.combine(date, datetime.max.time(), tzinfo=timezone.utc)
            
            first_join = sessions_collection.find_one(
                {
                    "user_id": user_id,
                    "event": "joined",
                    "start_time": {"$gte": day_start, "$lte": day_end}
                }, 
                sort=[("start_time", 1)]
            )
            
            last_leave = sessions_collection.find_one(
                {
                    "user_id": user_id,
                    "event": "left", 
                    "stop_time": {"$gte": day_start, "$lte": day_end}
                },
                sort=[("stop_time", -1)]
            )
            
            logger.info(f"Found session data for {user_id} on {date}")
            return first_join, last_leave

        except Exception as e:
            logger.error(f"Error getting session data: {e}", exc_info=True)
            return None, None

    def manage_user_session(self, user_id, action):
        """Start or stop a user session"""
        current_time = datetime.now(timezone.utc)
        
        if action == 'start':
            session_data = {
                "user_id": user_id,
                "channel": "wfh-monitoring",
                "start_time": current_time,
                "stop_time": None,
                "event": "joined",
                "timestamp": current_time
            }
            result = sessions_collection.insert_one(session_data)
            logger.info(f"✅ Started new session for user {user_id}")
            return result.inserted_id
            
        else:  # stop
            result = sessions_collection.update_one(
                {
                    "user_id": user_id,
                    "stop_time": None
                },
                {
                    "$set": {
                        "stop_time": current_time,
                        "event": "left",
                        "timestamp": current_time
                    }
                }
            )
            logger.info(f"✅ Stopped session for user {user_id}")
            return result.modified_count

# Create a singleton instance
session_service = SessionService()