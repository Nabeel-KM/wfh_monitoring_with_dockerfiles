from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
from bson import ObjectId

from ..services.mongodb import get_database
from ..models.database import User, Session
from ..utils.helpers import ensure_timezone_aware

router = APIRouter()

class SessionData(BaseModel):
    username: str
    display_name: Optional[str] = None
    channel: Optional[str] = None
    screen_shared: bool = False
    event: str
    timestamp: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

@router.post("/session")
async def handle_session(data: SessionData):
    """Handle session events (join, leave, start/stop streaming)."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        sessions = db.sessions
        
        # Validate event type
        if data.event not in ['joined', 'left', 'started_streaming', 'stopped_streaming']:
            raise HTTPException(status_code=400, detail="Invalid event type")
        
        # Get or create user
        user = await users.find_one({"username": data.username})
        if not user:
            user = {
                "username": data.username,
                "display_name": data.display_name or data.username,
                "created_at": datetime.now(timezone.utc)
            }
            result = await users.insert_one(user)
            user["_id"] = result.inserted_id
        
        # Update user's display_name if provided
        if data.display_name:
            await users.update_one(
                {"_id": user["_id"]},
                {"$set": {"display_name": data.display_name}}
            )
        
        current_time = datetime.now(timezone.utc)
        
        # Handle different events
        if data.event == "joined":
            # Create new session
            session = {
                "user_id": user["_id"],
                "channel": data.channel,
                "screen_shared": False,
                "screen_share_time": 0,
                "start_time": current_time,
                "stop_time": None,
                "event": "joined",
                "timestamp": current_time,
                "total_working_hours": 0
            }
            await sessions.insert_one(session)
            
        elif data.event == "left":
            # Find latest session
            latest_session = await sessions.find_one(
                {"user_id": user["_id"]},
                sort=[("timestamp", -1)]
            )
            
            if latest_session:
                start_time = latest_session.get("start_time")
                if start_time:
                    duration = (current_time - start_time).total_seconds()
                    await sessions.update_one(
                        {"_id": latest_session["_id"]},
                        {
                            "$set": {
                                "stop_time": current_time,
                                "channel": None,
                                "event": "left",
                                "timestamp": current_time,
                                "total_working_hours": int(duration)
                            }
                        }
                    )
            
        elif data.event == "started_streaming":
            # Find or create session
            latest_session = await sessions.find_one(
                {"user_id": user["_id"]},
                sort=[("timestamp", -1)]
            )
            
            if latest_session:
                await sessions.update_one(
                    {"_id": latest_session["_id"]},
                    {
                        "$set": {
                            "screen_shared": True,
                            "start_time": current_time,
                            "channel": data.channel,
                            "event": "started_streaming",
                            "timestamp": current_time
                        }
                    }
                )
            else:
                session = {
                    "user_id": user["_id"],
                    "channel": data.channel,
                    "screen_shared": True,
                    "screen_share_time": 0,
                    "start_time": current_time,
                    "stop_time": None,
                    "event": "started_streaming",
                    "timestamp": current_time,
                    "total_working_hours": 0
                }
                await sessions.insert_one(session)
                
        elif data.event == "stopped_streaming":
            latest_session = await sessions.find_one(
                {"user_id": user["_id"]},
                sort=[("timestamp", -1)]
            )
            
            if latest_session and latest_session.get("start_time"):
                start_time = latest_session["start_time"]
                duration = (current_time - start_time).total_seconds()
                
                await sessions.update_one(
                    {"_id": latest_session["_id"]},
                    {
                        "$inc": {"screen_share_time": int(duration)},
                        "$set": {
                            "screen_shared": False,
                            "start_time": None,
                            "event": "stopped_streaming",
                            "timestamp": current_time
                        }
                    }
                )
        
        return {
            "status": "success",
            "username": data.username,
            "event": data.event,
            "timestamp": current_time.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in handle_session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/session_status")
async def get_session_status(username: str):
    """Get current session status for a user."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        users = db.users
        sessions = db.sessions
        
        user = await users.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get latest session
        session = await sessions.find_one(
            {"user_id": user["_id"]},
            sort=[("timestamp", -1)]
        )
        
        return {
            "username": user["username"],
            "display_name": user.get("display_name", user["username"]),
            "screen_shared": session.get("screen_shared", False) if session else False,
            "channel": session.get("channel") if session else None,
            "timestamp": session.get("timestamp").isoformat() if session and session.get("timestamp") else None,
            "active_app": session.get("active_app") if session else None,
            "active_apps": session.get("active_apps", []) if session else [],
            "last_event": session.get("event") if session else None,
            "last_update": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_session_status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 