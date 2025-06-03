from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from ..services.mongodb import get_database
from ..models.database import Activity
from ..utils.helpers import ensure_timezone_aware, normalize_app_names

router = APIRouter(
    prefix="/activity",
    tags=["activity"],
    responses={404: {"description": "Not found"}},
)

class SystemInfo(BaseModel):
    platform: str
    version: str
    hostname: str

class ActivityData(BaseModel):
    username: str
    display_name: Optional[str] = None
    apps: Optional[Dict[str, float]] = Field(default_factory=dict)
    app_usage: Optional[Dict[str, float]] = Field(default_factory=dict)
    timestamp: Optional[str] = None
    date: Optional[str] = None
    app_sync_info: Optional[Dict[str, str]] = Field(default_factory=dict)
    idle_time: Optional[int] = 0
    total_active_time: Optional[float] = 0
    system_info: Optional[SystemInfo] = None

    model_config = ConfigDict(from_attributes=True)

@router.post("/")
async def track_activity(data: ActivityData):
    """Track user activity and active applications."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        activities = db.activities
        daily_summaries = db.daily_summaries
        
        # Get user
        user = await users.find_one({"username": data.username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Use current date if not provided
        current_date = data.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Use apps field if available, fall back to app_usage
        app_usage = data.apps or data.app_usage or {}
        
        # Normalize app names
        normalized_app_usage = normalize_app_names(app_usage)
        
        now_utc = datetime.now(timezone.utc)
        
        # Update activities collection
        for app_name, duration in normalized_app_usage.items():
            sync_ts = data.app_sync_info.get(app_name, data.timestamp)
            
            # Check for existing activity
            activity_doc = await activities.find_one({
                "user_id": user["_id"],
                "app_name": app_name,
                "date": current_date
            })
            
            last_sync = activity_doc.get("last_sync", "") if activity_doc else ""
            
            if not last_sync or sync_ts > last_sync:
                await activities.update_one(
                    {
                        "user_id": user["_id"],
                        "app_name": app_name,
                        "date": current_date
                    },
                    {
                        "$inc": {"total_time": duration},
                        "$set": {
                            "last_updated": now_utc,
                            "username": user['username'],
                            "last_sync": sync_ts
                        }
                    },
                    upsert=True
                )
        
        # Update daily summary
        total_time = sum(app_usage.values())
        
        update_data = {
            "$inc": {
                "total_active_time": total_time,
                "total_idle_time": data.idle_time
            },
            "$set": {
                "last_updated": now_utc,
                "username": user['username']
            }
        }
        
        await daily_summaries.update_one(
            {
                "user_id": user["_id"],
                "date": current_date
            },
            update_data,
            upsert=True
        )
        
        return {
            "status": "success",
            "username": data.username,
            "timestamp": now_utc.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in track_activity: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_activity_history(
    username: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100
):
    """Get activity history for a user."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        activities = db.activities
        
        # Get user
        user = await users.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Build query
        query = {"user_id": user["_id"]}
        
        if start_time or end_time:
            time_query = {}
            if start_time:
                time_query["$gte"] = ensure_timezone_aware(start_time)
            if end_time:
                time_query["$lte"] = ensure_timezone_aware(end_time)
            query["timestamp"] = time_query
        
        # Get activities
        cursor = activities.find(query).sort("timestamp", -1).limit(limit)
        activity_list = await cursor.to_list(length=limit)
        
        # Process activities
        processed_activities = []
        for activity in activity_list:
            processed_activities.append({
                "active_app": activity["active_app"],
                "active_apps": activity["active_apps"],
                "timestamp": activity["timestamp"].isoformat()
            })
        
        return {
            "username": username,
            "activities": processed_activities,
            "count": len(processed_activities),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_activity_history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/usage")
async def get_app_usage(
    username: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
):
    """Get application usage statistics for a user."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        activities = db.activities
        
        # Get user
        user = await users.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Build query
        query = {"user_id": user["_id"]}
        
        if start_time or end_time:
            time_query = {}
            if start_time:
                time_query["$gte"] = ensure_timezone_aware(start_time)
            if end_time:
                time_query["$lte"] = ensure_timezone_aware(end_time)
            query["timestamp"] = time_query
        
        # Get activities
        cursor = activities.find(query)
        activity_list = await cursor.to_list(length=None)
        
        # Process activities
        app_usage = {}
        for activity in activity_list:
            app_name = activity.get("app_name", "Unknown")
            duration = activity.get("total_time", 0)
            
            if app_name in app_usage:
                app_usage[app_name] += duration
            else:
                app_usage[app_name] = duration
        
        return {
            "username": username,
            "app_usage": app_usage,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_app_usage: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 