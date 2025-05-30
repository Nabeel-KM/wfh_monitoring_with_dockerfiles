from fastapi import APIRouter, HTTPException, Request, Query
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
import asyncio

from ..services.mongodb import get_database
from ..utils.helpers import ensure_timezone_aware, normalize_app_names, serialize_mongodb_doc

router = APIRouter()

class PaginationInfo(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int

class DashboardResponse(BaseModel):
    data: List[Dict[str, Any]]
    pagination: PaginationInfo

    model_config = ConfigDict(from_attributes=True)

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

async def get_user_dashboard_data(user: Dict[str, Any], current_date: datetime) -> Dict[str, Any]:
    """Get dashboard data for a single user"""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")

        # Get latest session
        latest_session = await db.sessions.find_one(
            {"user_id": user["_id"]},
            sort=[("timestamp", -1)]
        )

        # Get first join and last leave for today
        day_start = datetime.combine(current_date, datetime.min.time(), tzinfo=timezone.utc)
        day_end = datetime.combine(current_date, datetime.max.time(), tzinfo=timezone.utc)
        
        print(f"🔍 Calculating session time for user {user['username']} on {current_date}")
        print(f"📅 Day range: {day_start} to {day_end}")
        
        # Get first join and last leave for today
        first_join = await db.sessions.find_one({
            "user_id": user["_id"],
            "event": "joined",
            "start_time": {"$gte": day_start, "$lte": day_end}
        }, sort=[("start_time", 1)])
        
        last_leave = await db.sessions.find_one({
            "user_id": user["_id"],
            "event": "left",
            "stop_time": {"$gte": day_start, "$lte": day_end}
        }, sort=[("stop_time", -1)])
        
        # Calculate total session time from first join to last leave
        total_session_hours = 0
        if first_join and last_leave and first_join.get("start_time") and last_leave.get("stop_time"):
            first_join_time = ensure_timezone_aware(first_join["start_time"])
            last_leave_time = ensure_timezone_aware(last_leave["stop_time"])
            
            if last_leave_time > first_join_time:
                total_session_seconds = (last_leave_time - first_join_time).total_seconds()
                total_session_hours = round(total_session_seconds / 3600, 2)
                print(f"⏱️ Total session duration: {total_session_seconds} seconds (from {first_join_time} to {last_leave_time})")
            else:
                print(f"⚠️ Warning: Last leave time ({last_leave_time}) is before first join time ({first_join_time})")
        
        print(f"📊 Total session hours: {total_session_hours}")
        total_working_hours = total_session_hours  # Use the same value for both

        # Get app usage
        day_str = current_date.strftime("%Y-%m-%d")
        activities = await db.activities.find({
            "user_id": user["_id"],
            "date": day_str
        }).to_list(length=None)

        app_usage = [
            {"app_name": a["app_name"], "total_time": max(a.get("total_time", 0), 0)}
            for a in activities
        ] if activities else []

        # Get daily summary
        daily_summary = await db.daily_summaries.find_one({
            "user_id": user["_id"],
            "date": day_str
        })

        # Calculate total active time
        total_active_time = 0
        if daily_summary and "total_active_time" in daily_summary:
            total_active_time = daily_summary["total_active_time"]

        # Get most active app
        most_active_app = None
        most_used_app_time = 0
        if app_usage:
            most_active_app = max(app_usage, key=lambda x: x.get("total_time", 0))
            most_used_app = most_active_app.get("app_name")
            most_used_app_time = round(most_active_app.get("total_time", 0), 2)

        # Format timestamps
        timestamp = None
        if latest_session and latest_session.get("timestamp"):
            timestamp_dt = ensure_timezone_aware(latest_session.get("timestamp"))
            timestamp = timestamp_dt.isoformat()

        duty_start_time = None
        if first_join and first_join.get("start_time"):
            start_time_dt = ensure_timezone_aware(first_join.get("start_time"))
            duty_start_time = start_time_dt.isoformat()

        duty_end_time = None
        if last_leave and last_leave.get("stop_time"):
            end_time_dt = ensure_timezone_aware(last_leave.get("stop_time"))
            duty_end_time = end_time_dt.isoformat()

        return {
            "username": user["username"],
            "display_name": user.get("display_name", user["username"]),
            "channel": latest_session.get("channel") if latest_session else None,
            "screen_shared": latest_session.get("screen_shared", False) if latest_session else False,
            "timestamp": timestamp,
            "active_app": most_used_app,
            "active_apps": [a["app_name"] for a in app_usage if a.get("total_time", 0) > 0],
            "screen_share_time": latest_session.get("screen_share_time", 0) if latest_session else 0,
            "total_idle_time": daily_summary.get("total_idle_time", 0) if daily_summary else 0,
            "total_active_time": total_active_time,
            "total_session_time": total_session_hours,
            "total_working_hours": total_working_hours,
            "duty_start_time": duty_start_time,
            "duty_end_time": duty_end_time,
            "app_usage": app_usage,
            "most_used_app": most_used_app,
            "most_used_app_time": most_used_app_time
        }
    except Exception as e:
        print(f"❌ Error in get_user_dashboard_data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=1000)
):
    """Get dashboard data for all users with pagination"""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")

        # Get total count for pagination info
        total_users = await db.users.count_documents({})
        
        # Calculate skip value
        skip = (page - 1) * per_page
        
        # Get users for current page
        users = await db.users.find().skip(skip).limit(per_page).to_list(length=per_page)
        current_date = datetime.now(timezone.utc).date()
        
        # Process user data concurrently
        tasks = [get_user_dashboard_data(user, current_date) for user in users]
        dashboard_data = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out errors and None values
        dashboard_data = [data for data in dashboard_data if not isinstance(data, Exception) and data is not None]
        
        # Add pagination metadata
        response_data = {
            "data": dashboard_data,
            "pagination": {
                "total": total_users,
                "page": page,
                "per_page": per_page,
                "pages": (total_users + per_page - 1) // per_page
            }
        }
        
        return response_data
    except Exception as e:
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