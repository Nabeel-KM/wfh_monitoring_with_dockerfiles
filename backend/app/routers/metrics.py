from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict

from ..services.mongodb import get_database
from ..utils.helpers import ensure_timezone_aware, normalize_app_names

router = APIRouter()

class MetricsData(BaseModel):
    username: str
    date: str
    total_active_time: int = 0
    total_idle_time: int = 0
    total_session_time: float = 0.0
    productivity_score: float = 0.0
    focus_score: float = 0.0
    break_count: int = 0
    avg_session_length: float = 0.0
    productive_apps: List[Dict[str, Any]] = []
    distracting_apps: List[Dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)

@router.get("/metrics/system")
async def get_system_metrics():
    """Get system-wide metrics."""
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
        week_start = today_start - timedelta(days=today_start.weekday())
        
        # Get total users
        total_users = await users.count_documents({})
        
        # Get active users this week
        active_users = await sessions.distinct(
            "user_id",
            {"timestamp": {"$gte": week_start}}
        )
        active_users_count = len(active_users)
        
        # Get total sessions this week
        total_sessions = await sessions.count_documents({
            "timestamp": {"$gte": week_start}
        })
        
        # Get total activities this week
        total_activities = await activities.count_documents({
            "timestamp": {"$gte": week_start}
        })
        
        # Get average screen share time this week
        pipeline = [
            {"$match": {"timestamp": {"$gte": week_start}}},
            {"$group": {
                "_id": None,
                "avg_screen_share": {"$avg": "$screen_share_time"}
            }}
        ]
        result = await sessions.aggregate(pipeline).to_list(length=1)
        avg_screen_share = result[0]["avg_screen_share"] if result else 0
        
        # Get top applications this week
        pipeline = [
            {"$match": {"timestamp": {"$gte": week_start}}},
            {"$group": {
                "_id": "$active_app",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        top_apps = await activities.aggregate(pipeline).to_list(length=10)
        
        # Get daily summaries for the week
        pipeline = [
            {"$match": {"date": {"$gte": week_start.date()}}},
            {"$group": {
                "_id": "$date",
                "total_screen_share": {"$sum": "$total_screen_share_time"},
                "total_activities": {"$sum": "$total_activities"},
                "unique_users": {"$addToSet": "$user_id"}
            }},
            {"$sort": {"_id": 1}}
        ]
        daily_stats = await daily_summaries.aggregate(pipeline).to_list(length=None)
        
        # Process daily stats
        processed_daily_stats = []
        for stat in daily_stats:
            processed_daily_stats.append({
                "date": stat["_id"].strftime('%Y-%m-%d') if hasattr(stat["_id"], 'strftime') else str(stat["_id"]),
                "total_screen_share": stat["total_screen_share"],
                "total_activities": stat["total_activities"],
                "unique_users": len(stat["unique_users"])
            })
        
        return {
            "total_users": total_users,
            "active_users_this_week": active_users_count,
            "total_sessions_this_week": total_sessions,
            "total_activities_this_week": total_activities,
            "avg_screen_share_time": int(avg_screen_share),
            "top_applications": [
                {"app": app["_id"], "count": app["count"]}
                for app in top_apps
            ],
            "daily_stats": processed_daily_stats,
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        print(f"Error in get_system_metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics/user")
async def get_user_metrics(
    username: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """Get detailed metrics for a specific user."""
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
        
        # Set default date range if not provided
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=7)
        if not end_date:
            end_date = datetime.now(timezone.utc)
        
        # Ensure dates are timezone-aware
        start_date = ensure_timezone_aware(start_date)
        end_date = ensure_timezone_aware(end_date)
        
        # Get sessions in date range
        sessions_list = await sessions.find({
            "user_id": user["_id"],
            "timestamp": {
                "$gte": start_date,
                "$lte": end_date
            }
        }).to_list(length=None)
        
        # Get activities in date range
        activities_list = await activities.find({
            "user_id": user["_id"],
            "timestamp": {
                "$gte": start_date,
                "$lte": end_date
            }
        }).to_list(length=None)
        
        # Get daily summaries in date range
        daily_summaries_list = await daily_summaries.find({
            "user_id": user["_id"],
            "date": {
                "$gte": start_date.date(),
                "$lte": end_date.date()
            }
        }).to_list(length=None)
        
        # Calculate app usage
        app_usage = {}
        for activity in activities_list:
            active_app = activity.get("active_app")
            if active_app:
                if active_app in app_usage:
                    app_usage[active_app] += 1
                else:
                    app_usage[active_app] = 1
        
        # Normalize and sort app usage
        normalized_usage = normalize_app_names(app_usage)
        sorted_usage = dict(sorted(normalized_usage.items(), key=lambda x: x[1], reverse=True))
        
        # Calculate total screen share time
        total_screen_share = sum(session.get("screen_share_time", 0) for session in sessions_list)
        
        # Process daily summaries
        processed_summaries = []
        for summary in daily_summaries_list:
            processed_summaries.append({
                "date": summary["date"].strftime('%Y-%m-%d') if hasattr(summary["date"], 'strftime') else str(summary["date"]),
                "total_screen_share_time": summary.get("total_screen_share_time", 0),
                "total_activities": summary.get("total_activities", 0),
                "app_usage": summary.get("app_usage", {})
            })
        
        return {
            "username": username,
            "display_name": user.get("display_name", username),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_sessions": len(sessions_list),
            "total_activities": len(activities_list),
            "total_screen_share_time": total_screen_share,
            "app_usage": sorted_usage,
            "daily_summaries": processed_summaries,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_user_metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))