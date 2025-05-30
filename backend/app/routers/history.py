from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict

from ..services.mongodb import get_collections
from ..utils.helpers import ensure_timezone_aware, normalize_app_names

router = APIRouter()

class HistoryData(BaseModel):
    username: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    activities: List[Dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)

@router.get("/history/sessions")
async def get_session_history(
    username: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100
):
    """Get session history for a user."""
    try:
        collections = get_collections()
        users = collections["users"]
        sessions = collections["sessions"]
        
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
        
        # Build query
        query = {
            "user_id": user["_id"],
            "timestamp": {
                "$gte": start_date,
                "$lte": end_date
            }
        }
        
        # Get sessions
        cursor = sessions.find(query).sort("timestamp", -1).limit(limit)
        session_list = await cursor.to_list(length=limit)
        
        # Process sessions
        processed_sessions = []
        for session in session_list:
            processed_sessions.append({
                "session_id": str(session["_id"]),
                "event": session.get("event"),
                "screen_shared": session.get("screen_shared", False),
                "screen_share_time": session.get("screen_share_time", 0),
                "start_time": session.get("start_time").isoformat() if session.get("start_time") else None,
                "stop_time": session.get("stop_time").isoformat() if session.get("stop_time") else None,
                "timestamp": session.get("timestamp").isoformat() if session.get("timestamp") else None,
                "active_app": session.get("active_app"),
                "active_apps": session.get("active_apps", [])
            })
        
        return {
            "username": username,
            "sessions": processed_sessions,
            "count": len(processed_sessions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/activities")
async def get_activity_history(
    username: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100
):
    """Get activity history for a user."""
    try:
        collections = get_collections()
        users = collections["users"]
        activities = collections["activities"]
        
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
        
        # Build query
        query = {
            "user_id": user["_id"],
            "timestamp": {
                "$gte": start_date,
                "$lte": end_date
            }
        }
        
        # Get activities
        cursor = activities.find(query).sort("timestamp", -1).limit(limit)
        activity_list = await cursor.to_list(length=limit)
        
        # Process activities
        processed_activities = []
        for activity in activity_list:
            processed_activities.append({
                "activity_id": str(activity["_id"]),
                "session_id": str(activity["session_id"]),
                "active_app": activity.get("active_app"),
                "active_apps": activity.get("active_apps", []),
                "timestamp": activity.get("timestamp").isoformat() if activity.get("timestamp") else None
            })
        
        return {
            "username": username,
            "activities": processed_activities,
            "count": len(processed_activities)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/daily_summaries")
async def get_daily_summaries(
    username: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """Get daily summaries for a user."""
    try:
        collections = get_collections()
        users = collections["users"]
        daily_summaries = collections["daily_summaries"]
        
        # Get user
        user = await users.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Set default date range if not provided
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)
        
        # Ensure dates are timezone-aware
        start_date = ensure_timezone_aware(start_date)
        end_date = ensure_timezone_aware(end_date)
        
        # Build query
        query = {
            "user_id": user["_id"],
            "date": {
                "$gte": start_date.date(),
                "$lte": end_date.date()
            }
        }
        
        # Get daily summaries
        cursor = daily_summaries.find(query).sort("date", -1)
        summary_list = await cursor.to_list(length=None)
        
        # Process summaries
        processed_summaries = []
        for summary in summary_list:
            processed_summaries.append({
                "date": summary["date"].isoformat(),
                "total_screen_share_time": summary.get("total_screen_share_time", 0),
                "total_activities": summary.get("total_activities", 0),
                "app_usage": summary.get("app_usage", {}),
                "sessions": summary.get("sessions", 0),
                "average_session_duration": summary.get("average_session_duration", 0)
            })
        
        return {
            "username": username,
            "summaries": processed_summaries,
            "count": len(processed_summaries)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/report")
async def generate_report(
    username: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """Generate a comprehensive report for a user."""
    try:
        collections = get_collections()
        users = collections["users"]
        sessions = collections["sessions"]
        activities = collections["activities"]
        daily_summaries = collections["daily_summaries"]
        
        # Get user
        user = await users.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Set default date range if not provided
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)
        
        # Ensure dates are timezone-aware
        start_date = ensure_timezone_aware(start_date)
        end_date = ensure_timezone_aware(end_date)
        
        # Get sessions
        sessions_list = await sessions.find({
            "user_id": user["_id"],
            "timestamp": {
                "$gte": start_date,
                "$lte": end_date
            }
        }).to_list(length=None)
        
        # Get activities
        activities_list = await activities.find({
            "user_id": user["_id"],
            "timestamp": {
                "$gte": start_date,
                "$lte": end_date
            }
        }).to_list(length=None)
        
        # Get daily summaries
        summaries_list = await daily_summaries.find({
            "user_id": user["_id"],
            "date": {
                "$gte": start_date.date(),
                "$lte": end_date.date()
            }
        }).to_list(length=None)
        
        # Calculate statistics
        total_sessions = len(sessions_list)
        total_activities = len(activities_list)
        total_screen_share = sum(session.get("screen_share_time", 0) for session in sessions_list)
        
        # Calculate app usage
        app_usage = {}
        for activity in activities_list:
            active_app = activity["active_app"]
            if active_app in app_usage:
                app_usage[active_app] += 1
            else:
                app_usage[active_app] = 1
        
        # Normalize and sort app usage
        normalized_usage = normalize_app_names(app_usage)
        sorted_usage = dict(sorted(normalized_usage.items(), key=lambda x: x[1], reverse=True))
        
        # Calculate daily averages
        days_count = (end_date.date() - start_date.date()).days + 1
        avg_daily_sessions = total_sessions / days_count if days_count > 0 else 0
        avg_daily_activities = total_activities / days_count if days_count > 0 else 0
        avg_daily_screen_share = total_screen_share / days_count if days_count > 0 else 0
        
        return {
            "username": username,
            "display_name": user.get("display_name", username),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days_count
            },
            "summary": {
                "total_sessions": total_sessions,
                "total_activities": total_activities,
                "total_screen_share_time": total_screen_share,
                "avg_daily_sessions": round(avg_daily_sessions, 2),
                "avg_daily_activities": round(avg_daily_activities, 2),
                "avg_daily_screen_share": round(avg_daily_screen_share, 2)
            },
            "app_usage": sorted_usage,
            "daily_summaries": [
                {
                    "date": summary["date"].isoformat(),
                    "total_screen_share_time": summary.get("total_screen_share_time", 0),
                    "total_activities": summary.get("total_activities", 0),
                    "sessions": summary.get("sessions", 0)
                }
                for summary in summaries_list
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 