from fastapi import APIRouter, HTTPException, Request, Query
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
import asyncio

from ..services.mongodb import get_database
from ..utils.helpers import ensure_timezone_aware, normalize_app_names, serialize_mongodb_doc

router = APIRouter()

class DailyData(BaseModel):
    date: str
    first_activity: Optional[str]
    last_activity: Optional[str]
    total_session_time: float
    total_active_time: float
    total_idle_time: float
    app_usage: List[Dict[str, Any]]
    most_used_app: Optional[str]
    most_used_app_time: float

class HistoryData(BaseModel):
    username: str
    display_name: str
    days: List[DailyData]

    model_config = ConfigDict(from_attributes=True)

async def get_session_data(user_id: str, day_str: str, sessions_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Get session data for a specific day"""
    return next((s for s in sessions_data if s["_id"]["user_id"] == user_id and s["_id"]["date"] == day_str), None)

async def get_daily_data(user_id: str, day_str: str, session_data: Optional[Dict[str, Any]], db) -> Dict[str, Any]:
    """Get daily data for a user"""
    try:
        # Get first join and last leave times
        first_join_time = None
        last_leave_time = None
        total_session_hours = 0
        
        if session_data:
            first_join_time = session_data.get("first_join")
            last_leave_time = session_data.get("last_leave")
            
            if first_join_time and last_leave_time:
                first_join_time = ensure_timezone_aware(first_join_time)
                last_leave_time = ensure_timezone_aware(last_leave_time)
                
                if last_leave_time > first_join_time:
                    total_session_seconds = (last_leave_time - first_join_time).total_seconds()
                    total_session_hours = round(total_session_seconds / 3600, 2)

        # Get activities
        activities = await db.activities.find({
            "user_id": user_id,
            "date": day_str
        }).to_list(length=None)

        # Process app usage
        app_usage = [
            {"app_name": a["app_name"], "total_time": max(a.get("total_time", 0), 0)}
            for a in activities
        ] if activities else []

        # Get most active app
        most_active_app = None
        most_used_app_time = 0
        if app_usage:
            most_active_app = max(app_usage, key=lambda x: x.get("total_time", 0))
            most_used_app = most_active_app.get("app_name")
            most_used_app_time = round(most_active_app.get("total_time", 0), 2)

        # Get daily summary
        daily_summary = await db.daily_summaries.find_one({
            "user_id": user_id,
            "date": day_str
        })

        # Format timestamps
        first_activity = first_join_time.isoformat() if first_join_time else None
        last_activity = last_leave_time.isoformat() if last_leave_time else None

        # Calculate active time
        active_time = 0
        if daily_summary and "total_active_time" in daily_summary:
            active_time = round(daily_summary.get("total_active_time", 0) / 60, 2)  # Convert minutes to hours

        # Calculate idle time
        idle_time = 0
        if daily_summary and "total_idle_time" in daily_summary:
            idle_time = round(daily_summary.get("total_idle_time", 0) / 60, 2)  # Convert minutes to hours

        return {
            "date": day_str,
            "first_activity": first_activity,
            "last_activity": last_activity,
            "total_session_time": total_session_hours,
            "total_active_time": active_time,
            "total_idle_time": idle_time,
            "app_usage": app_usage,
            "most_used_app": most_used_app,
            "most_used_app_time": most_used_app_time
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history", response_model=List[HistoryData])
async def get_history(
    username: Optional[str] = None,
    days: int = Query(30, ge=1, le=365)
):
    """Get user history data"""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")

        # Get users
        if username:
            user = await db.users.find_one({"username": username})
            if not user:
                raise HTTPException(status_code=404, detail=f"User not found: {username}")
            users = [user]
        else:
            users = await db.users.find().to_list(length=None)

        if not users:
            raise HTTPException(status_code=404, detail="No users found")

        # Calculate date range
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days-1)

        # Get sessions data
        pipeline = [
            {"$match": {
                "user_id": {"$in": [user["_id"] for user in users]},
                "$or": [
                    {"start_time": {"$gte": start_date, "$lte": end_date}},
                    {"stop_time": {"$gte": start_date, "$lte": end_date}}
                ]
            }},
            {"$sort": {"start_time": 1}},
            {"$group": {
                "_id": {
                    "user_id": "$user_id",
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$start_time"}}
                },
                "first_join": {"$first": "$start_time"},
                "last_leave": {"$last": "$stop_time"}
            }}
        ]
        sessions_data = await db.sessions.aggregate(pipeline).to_list(length=None)

        # Process user history
        history_data = []
        for user in users:
            try:
                user_history = {
                    "username": user["username"],
                    "display_name": user.get("display_name", user["username"]),
                    "days": []
                }

                for i in range(days):
                    day = start_date + timedelta(days=i)
                    day_str = day.strftime("%Y-%m-%d")
                    session_data = await get_session_data(user["_id"], day_str, sessions_data)
                    daily_data = await get_daily_data(user["_id"], day_str, session_data, db)
                    user_history["days"].append(daily_data)

                history_data.append(user_history)
            except Exception as e:
                # Log error but continue processing other users
                print(f"Error processing history for user {user.get('username')}: {e}")
                continue

        return history_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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