from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict

from ..services.mongodb import get_database
from ..utils.helpers import ensure_timezone_aware, normalize_app_names

router = APIRouter()

class DashboardData(BaseModel):
    username: str
    display_name: Optional[str] = None
    active_app: Optional[str] = None
    active_apps: List[str] = []
    screen_shared: bool = False
    channel: Optional[str] = None
    timestamp: Optional[datetime] = None
    total_active_time: int = 0
    total_idle_time: int = 0
    total_session_time: float = 0.0
    total_working_hours: float = 0.0

    model_config = ConfigDict(from_attributes=True)

@router.get("/dashboard")
async def get_dashboard():
    """Get dashboard data."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        sessions = db.sessions
        activities = db.activities
        daily_summaries = db.daily_summaries
        
        # Get current time
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_str = today_start.strftime("%Y-%m-%d")  # Convert to string format
        
        # Get all users
        users_list = await users.find().to_list(length=None)
        
        # Process each user's data
        dashboard_data = []
        for user in users_list:
            # Get latest session
            latest_session = await sessions.find_one(
                {"user_id": user["_id"]},
                sort=[("timestamp", -1)]
            )
            
            # Get today's activities
            today_activities = await activities.find({
                "user_id": user["_id"],
                "timestamp": {"$gte": today_start}
            }).to_list(length=None)
            
            # Get today's daily summary using string date
            today_summary = await daily_summaries.find_one({
                "user_id": user["_id"],
                "date": today_str
            })
            
            # Calculate app usage
            app_usage = {}
            for activity in today_activities:
                active_app = activity.get("active_app")
                if active_app:
                    if active_app in app_usage:
                        app_usage[active_app] += 1
                    else:
                        app_usage[active_app] = 1
            
            # Normalize and sort app usage
            normalized_usage = normalize_app_names(app_usage)
            sorted_usage = dict(sorted(normalized_usage.items(), key=lambda x: x[1], reverse=True))
            
            # Get most active app
            most_active_app = max(sorted_usage.items(), key=lambda x: x[1])[0] if sorted_usage else None
            
            # Create user dashboard data
            user_data = {
                "username": user["username"],
                "display_name": user.get("display_name", user["username"]),
                "active_app": most_active_app,
                "active_apps": list(sorted_usage.keys()),
                "screen_shared": latest_session.get("screen_shared", False) if latest_session else False,
                "channel": latest_session.get("channel") if latest_session else None,
                "timestamp": latest_session.get("timestamp").isoformat() if latest_session and latest_session.get("timestamp") else None,
                "total_active_time": today_summary.get("total_active_time", 0) if today_summary else 0,
                "total_idle_time": today_summary.get("total_idle_time", 0) if today_summary else 0,
                "total_session_time": today_summary.get("total_session_time", 0) if today_summary else 0,
                "total_working_hours": today_summary.get("total_working_hours", 0) if today_summary else 0
            }
            
            dashboard_data.append(user_data)
        
        return {
            "data": dashboard_data,
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        print(f"Error in get_dashboard: {str(e)}")  # Add logging
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard/overview")
async def get_dashboard_overview():
    """Get overview statistics for the dashboard."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        sessions = db.sessions
        activities = db.activities
        daily_summaries = db.daily_summaries
        
        # Get current time
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get total users
        total_users = await users.count_documents({})
        
        # Get active users today
        active_users = await sessions.distinct(
            "user_id",
            {"timestamp": {"$gte": today_start}}
        )
        active_users_count = len(active_users)
        
        # Get total sessions today
        total_sessions = await sessions.count_documents({
            "timestamp": {"$gte": today_start}
        })
        
        # Get total activities today
        total_activities = await activities.count_documents({
            "timestamp": {"$gte": today_start}
        })
        
        # Get average screen share time today
        pipeline = [
            {"$match": {"timestamp": {"$gte": today_start}}},
            {"$group": {
                "_id": None,
                "avg_screen_share": {"$avg": "$screen_share_time"}
            }}
        ]
        result = await sessions.aggregate(pipeline).to_list(length=1)
        avg_screen_share = result[0]["avg_screen_share"] if result else 0
        
        # Get top applications today
        pipeline = [
            {"$match": {"timestamp": {"$gte": today_start}}},
            {"$group": {
                "_id": "$active_app",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        top_apps = await activities.aggregate(pipeline).to_list(length=5)
        
        # Get daily summary
        daily_summary = await daily_summaries.find_one({
            "date": today_start.date()
        })
        
        return {
            "total_users": total_users,
            "active_users_today": active_users_count,
            "total_sessions_today": total_sessions,
            "total_activities_today": total_activities,
            "avg_screen_share_time": int(avg_screen_share),
            "top_applications": [
                {"app": app["_id"], "count": app["count"]}
                for app in top_apps
            ],
            "daily_summary": daily_summary if daily_summary else None
        }
        
    except Exception as e:
        print(f"Error in get_dashboard_overview: {str(e)}")  # Add logging
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard/user_stats")
async def get_user_stats(username: str):
    """Get detailed statistics for a specific user."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        sessions = db.sessions
        activities = db.activities
        daily_summaries = db.daily_summaries
        
        # Get user
        user = await users.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get current time
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get today's session
        today_session = await sessions.find_one(
            {
                "user_id": user["_id"],
                "timestamp": {"$gte": today_start}
            },
            sort=[("timestamp", -1)]
        )
        
        # Get today's activities
        today_activities = await activities.find(
            {
                "user_id": user["_id"],
                "timestamp": {"$gte": today_start}
            }
        ).to_list(length=None)
        
        # Get today's daily summary
        today_summary = await daily_summaries.find_one({
            "user_id": user["_id"],
            "date": today_start.date()
        })
        
        # Calculate app usage
        app_usage = {}
        for activity in today_activities:
            active_app = activity.get("active_app")
            if active_app:
                if active_app in app_usage:
                    app_usage[active_app] += 1
                else:
                    app_usage[active_app] = 1
        
        # Normalize and sort app usage
        normalized_usage = normalize_app_names(app_usage)
        sorted_usage = dict(sorted(normalized_usage.items(), key=lambda x: x[1], reverse=True))
        
        return {
            "username": username,
            "display_name": user.get("display_name", username),
            "current_session": {
                "screen_shared": today_session.get("screen_shared", False) if today_session else False,
                "screen_share_time": today_session.get("screen_share_time", 0) if today_session else 0,
                "start_time": today_session.get("start_time").isoformat() if today_session and today_session.get("start_time") else None,
                "stop_time": today_session.get("stop_time").isoformat() if today_session and today_session.get("stop_time") else None
            },
            "today_stats": {
                "total_activities": len(today_activities),
                "total_active_time": today_summary.get("total_active_time", 0) if today_summary else 0,
                "total_idle_time": today_summary.get("total_idle_time", 0) if today_summary else 0,
                "total_session_time": today_summary.get("total_session_time", 0) if today_summary else 0,
                "total_working_hours": today_summary.get("total_working_hours", 0) if today_summary else 0
            },
            "app_usage": sorted_usage
        }
        
    except Exception as e:
        print(f"Error in get_user_stats: {str(e)}")  # Add logging
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard/active_users")
async def get_active_users():
    """Get list of currently active users."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        sessions = db.sessions
        
        # Get current time
        now = datetime.now(timezone.utc)
        five_minutes_ago = now - timedelta(minutes=5)
        
        # Get active sessions
        active_sessions = await sessions.find({
            "timestamp": {"$gte": five_minutes_ago}
        }).to_list(length=None)
        
        # Get unique user IDs from active sessions
        active_user_ids = list(set(session["user_id"] for session in active_sessions))
        
        # Get user details
        active_users = await users.find({
            "_id": {"$in": active_user_ids}
        }).to_list(length=None)
        
        # Process user data
        active_users_data = []
        for user in active_users:
            # Get latest session for this user
            latest_session = next(
                (s for s in active_sessions if s["user_id"] == user["_id"]),
                None
            )
            
            active_users_data.append({
                "username": user["username"],
                "display_name": user.get("display_name", user["username"]),
                "screen_shared": latest_session.get("screen_shared", False) if latest_session else False,
                "channel": latest_session.get("channel") if latest_session else None,
                "last_activity": latest_session.get("timestamp").isoformat() if latest_session and latest_session.get("timestamp") else None
            })
        
        return {
            "active_users": active_users_data,
            "count": len(active_users_data),
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        print(f"Error in get_active_users: {str(e)}")  # Add logging
        raise HTTPException(status_code=500, detail=str(e)) 