from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta
import psutil
import time
from ..services.mongodb import get_database

router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    health_data = {
        "status": "healthy",
        "components": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Check database connection
    try:
        start_time = time.time()
        db = await get_database()
        if db is None:
            raise Exception("Database connection not available")
            
        await db.command("ping")
        db_response_time = time.time() - start_time
        
        health_data["components"]["database"] = {
            "status": "connected",
            "response_time_ms": round(db_response_time * 1000, 2)
        }
    except Exception as e:
        print(f"Database health check error: {str(e)}")
        health_data["status"] = "unhealthy"
        health_data["components"]["database"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Check memory usage
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        health_data["components"]["memory"] = {
            "status": "ok" if memory_mb < 500 else "warning",
            "usage_mb": round(memory_mb, 2)
        }
    except Exception as e:
        print(f"Memory health check error: {str(e)}")
        health_data["components"]["memory"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    # Check MongoDB connection pool
    try:
        if db is not None:
            server_status = await db.command("serverStatus")
            conn_stats = server_status.get("connections", {})
            current = conn_stats.get("current", 0)
            available = conn_stats.get("available", 0)
            max_conns = current + available
            usage_percent = (current / max_conns * 100) if max_conns > 0 else 0
            
            health_data["components"]["db_pool"] = {
                "status": "ok" if usage_percent < 80 else "warning",
                "current": current,
                "available": available,
                "usage_percent": round(usage_percent, 1)
            }
        else:
            health_data["components"]["db_pool"] = {
                "status": "error",
                "error": "Database connection not available"
            }
    except Exception as e:
        print(f"DB pool health check error: {str(e)}")
        health_data["components"]["db_pool"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    # Return appropriate status code
    status_code = 200 if health_data["status"] == "healthy" else 500
    return health_data

@router.get("/stats")
async def get_stats():
    """Get system statistics and metrics."""
    try:
        db = await get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection not available")
            
        # Get collection stats
        users_count = await db.users.count_documents({})
        sessions_count = await db.sessions.count_documents({})
        activities_count = await db.activities.count_documents({})
        summaries_count = await db.daily_summaries.count_documents({})
        
        # Get active users (users with activity in the last 24 hours)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        active_users = len(await db.daily_summaries.distinct("user_id", {
            "last_updated": {"$gte": yesterday}
        }))
        
        # Get top apps across all users for today
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pipeline = [
            {"$match": {"date": today}},
            {"$group": {"_id": "$app_name", "total_time": {"$sum": "$total_time"}}},
            {"$sort": {"total_time": -1}},
            {"$limit": 10}
        ]
        top_apps = await db.activities.aggregate(pipeline).to_list(None)
        
        return {
            "database": {
                "users": users_count,
                "sessions": sessions_count,
                "activities": activities_count,
                "summaries": summaries_count,
                "active_users_24h": active_users
            },
            "top_apps_today": [{"app": app["_id"], "minutes": app["total_time"]} for app in top_apps],
            "server_time": datetime.now(timezone.utc).isoformat(),
            "uptime": time.time() - app.start_time if hasattr(app, 'start_time') else 0
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 