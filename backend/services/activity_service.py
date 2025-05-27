"""
Activity service for handling activity-related operations.
"""
import logging
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from mongodb import activities_collection, app_usage_collection, daily_summaries_collection, sessions_collection

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
    
    def update_total_active_time(self, user_id, date, total_active_time):
        """Update total active time for a user on a specific date"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
            
        result = daily_summaries_collection.update_one(
            {
                "user_id": user_id,
                "date": date
            },
            {
                "$inc": {
                    "total_active_time": total_active_time
                },
                "$set": {
                    "last_updated": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        return result.modified_count > 0 or result.upserted_id is not None
    
    def calculate_productivity_metrics(self, user, current_date):
        """Calculate productivity metrics for a user on a specific date"""
        if isinstance(current_date, str):
            day_str = current_date
        else:
            day_str = current_date.strftime("%Y-%m-%d")
        
        # Get daily summary
        daily_summary = daily_summaries_collection.find_one({
            "user_id": user["_id"],
            "date": day_str
        })
        
        # Get activities
        activities = list(activities_collection.find({
            "user_id": user["_id"],
            "date": day_str
        }))
        
        # Get sessions
        if isinstance(current_date, str):
            current_date = datetime.strptime(current_date, "%Y-%m-%d").date()
            
        day_start = datetime.combine(current_date, datetime.min.time(), tzinfo=timezone.utc)
        day_end = datetime.combine(current_date, datetime.max.time(), tzinfo=timezone.utc)
        
        first_join = sessions_collection.find_one({
            "user_id": user["_id"],
            "event": "joined",
            "start_time": {"$gte": day_start, "$lte": day_end}
        }, sort=[("start_time", 1)])
        
        last_leave = sessions_collection.find_one({
            "user_id": user["_id"],
            "event": "left",
            "stop_time": {"$gte": day_start, "$lte": day_end}
        }, sort=[("stop_time", -1)])
        
        # Calculate total session hours
        total_session_hours = 0
        if first_join and last_leave and first_join.get("start_time") and last_leave.get("stop_time"):
            first_join_time = first_join["start_time"]
            last_leave_time = last_leave["stop_time"]
            
            if last_leave_time > first_join_time:
                total_session_seconds = (last_leave_time - first_join_time).total_seconds()
                total_session_hours = round(total_session_seconds / 3600, 2)
        
        # Calculate total working hours (sum of all sessions)
        sessions = list(sessions_collection.find({
            "user_id": user["_id"],
            "start_time": {"$gte": day_start, "$lte": day_end},
            "stop_time": {"$ne": None}
        }))
        
        total_working_hours = 0
        for session in sessions:
            if session.get("start_time") and session.get("stop_time"):
                start_time = session["start_time"]
                stop_time = session["stop_time"]
                if stop_time > start_time:
                    duration = (stop_time - start_time).total_seconds()
                    total_working_hours += duration
        
        total_working_hours = round(total_working_hours / 3600, 2)
        
        # Calculate metrics
        metrics = {
            "total_session_hours": total_session_hours,
            "total_working_hours": total_working_hours,
            "active_hours": 0,
            "idle_hours": 0,
            "productivity_score": 0,
            "focus_score": 0,
            "break_count": 0,
            "avg_session_length": 0,
            "productive_apps": [],
            "distracting_apps": []
        }
        
        if daily_summary:
            # Active time in hours
            active_minutes = daily_summary.get("total_active_time", 0)
            metrics["active_hours"] = round(active_minutes / 60, 2)
            
            # Idle time in hours
            idle_minutes = daily_summary.get("total_idle_time", 0)
            metrics["idle_hours"] = round(idle_minutes / 60, 2)
            
            # If session time is 0 but we have active time, use active time for session time
            if total_session_hours == 0 and metrics["active_hours"] > 0:
                total_session_hours = metrics["active_hours"]
                metrics["total_session_hours"] = total_session_hours
            
            # Productivity score (active time / session time)
            if total_session_hours > 0:
                metrics["productivity_score"] = round((metrics["active_hours"] / total_session_hours) * 100, 1)
            
            # Focus score (longest continuous active period)
            app_summaries = daily_summary.get("app_summaries", [])
            if app_summaries:
                # Calculate time gaps between summaries
                timestamps = []
                for s in app_summaries:
                    if "timestamp" in s:
                        try:
                            if isinstance(s["timestamp"], str):
                                timestamps.append(datetime.fromisoformat(s["timestamp"]))
                            else:
                                timestamps.append(s["timestamp"])
                        except (ValueError, TypeError):
                            pass
                
                if len(timestamps) > 1:
                    timestamps.sort()
                    gaps = [(timestamps[i+1] - timestamps[i]).total_seconds() / 60 for i in range(len(timestamps)-1)]
                    metrics["break_count"] = sum(1 for gap in gaps if gap > 15)  # Breaks > 15 minutes
                    
                    # Focus score based on consistency of activity
                    if gaps:
                        avg_gap = sum(gaps) / len(gaps)
                        metrics["focus_score"] = round(100 / (1 + avg_gap/30), 1)  # Higher score for smaller gaps
        
        # Categorize apps
        productive_apps = []
        distracting_apps = []
        
        # Define productive and distracting app categories
        productive_categories = ["code", "terminal", "browser", "office", "ide", "editor"]
        distracting_categories = ["social", "game", "entertainment", "messaging"]
        
        for activity in activities:
            app_name = activity.get("app_name", "").lower() if activity.get("app_name") else ""
            duration = activity.get("total_time", 0)
            
            # Simple categorization based on app name
            if any(category in app_name for category in productive_categories):
                productive_apps.append({"app": app_name, "duration": duration})
            elif any(category in app_name for category in distracting_categories):
                distracting_apps.append({"app": app_name, "duration": duration})
        
        # Sort by duration
        productive_apps.sort(key=lambda x: x["duration"], reverse=True)
        distracting_apps.sort(key=lambda x: x["duration"], reverse=True)
        
        metrics["productive_apps"] = productive_apps[:5]  # Top 5
        metrics["distracting_apps"] = distracting_apps[:5]  # Top 5
        
        # Calculate average session length
        session_durations = []
        for session in sessions:
            if session.get("start_time") and session.get("stop_time"):
                start = session["start_time"]
                stop = session["stop_time"]
                if stop > start:
                    duration = (stop - start).total_seconds() / 3600  # hours
                    session_durations.append(duration)
        
        if session_durations:
            metrics["avg_session_length"] = round(sum(session_durations) / len(session_durations), 2)
        
        return metrics

# Create a singleton instance
activity_service = ActivityService()