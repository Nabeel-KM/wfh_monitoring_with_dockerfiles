from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict

from ..services.mongodb import get_database
from ..models.database import Activity
from ..utils.helpers import ensure_timezone_aware, normalize_app_names

router = APIRouter()

class ActivityData(BaseModel):
    username: str
    active_app: str
    active_apps: List[str]
    timestamp: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

@router.post("/activity")
async def track_activity(data: ActivityData):
    """Track user activity and active applications."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        activities = db.activities
        sessions = db.sessions
        
        # Get user
        user = await users.find_one({"username": data.username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Ensure timestamp is timezone-aware
        timestamp = ensure_timezone_aware(data.timestamp or datetime.now(timezone.utc))
        
        # Get current session
        session = await sessions.find_one(
            {"user_id": user["_id"]},
            sort=[("timestamp", -1)]
        )
        
        if not session:
            raise HTTPException(status_code=400, detail="No active session found")
        
        # Create activity record
        activity = {
            "user_id": user["_id"],
            "session_id": session["_id"],
            "active_app": data.active_app,
            "active_apps": data.active_apps,
            "timestamp": timestamp
        }
        
        await activities.insert_one(activity)
        
        # Update session with current activity
        await sessions.update_one(
            {"_id": session["_id"]},
            {
                "$set": {
                    "active_app": data.active_app,
                    "active_apps": data.active_apps,
                    "last_activity": timestamp
                }
            }
        )
        
        return {
            "status": "success",
            "username": data.username,
            "active_app": data.active_app,
            "timestamp": timestamp.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in track_activity: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/activity_history")
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

@router.get("/app_usage")
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
        
        # Process app usage
        app_usage = {}
        for activity in activity_list:
            active_app = activity.get("active_app")
            if active_app:
                if active_app in app_usage:
                    app_usage[active_app] += 1
                else:
                    app_usage[active_app] = 1
        
        # Normalize app names
        normalized_usage = normalize_app_names(app_usage)
        
        # Sort by usage count
        sorted_usage = dict(sorted(normalized_usage.items(), key=lambda x: x[1], reverse=True))
        
        return {
            "username": username,
            "app_usage": sorted_usage,
            "total_activities": len(activity_list),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_app_usage: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 