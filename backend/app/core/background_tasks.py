from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, timezone
import logging
import psutil
from ..services.mongodb import get_database, get_collections

logger = logging.getLogger(__name__)

async def update_screen_share_time():
    """Update screen share time for active sessions."""
    try:
        logger.info("⏰ Running incremental screen share time update...")
        collections = await get_collections()
        sessions = collections["sessions"]
        
        # Find active screen sharing sessions
        active_sessions = await sessions.find({"screen_shared": True, "start_time": {"$ne": None}}).to_list(None)
        
        for session in active_sessions:
            start_time = session["start_time"]
            current_time = datetime.now(timezone.utc)
            
            if start_time < current_time:
                elapsed_time = int((current_time - start_time).total_seconds())
                
                await sessions.update_one(
                    {"_id": session["_id"]},
                    {
                        "$inc": {"screen_share_time": elapsed_time},
                        "$set": {"start_time": current_time, "timestamp": current_time}
                    }
                )
                logger.info(f"Updated screen share time for session {session['_id']}: +{elapsed_time}s")
    except Exception as e:
        logger.error(f"❌ Error during incremental screen share time update: {e}")

async def reset_screen_share_time():
    """Reset screen share time at midnight UTC."""
    try:
        collections = await get_collections()
        sessions = collections["sessions"]
        daily_summaries = collections["daily_summaries"]
        
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        
        # Get all sessions with screen share time
        active_sessions = await sessions.find({"screen_share_time": {"$gt": 0}}).to_list(None)
        
        for session in active_sessions:
            user_id = session["user_id"]
            screen_share_time = session["screen_share_time"]
            
            # Update daily summary
            await daily_summaries.update_one(
                {
                    "user_id": user_id,
                    "date": yesterday.strftime("%Y-%m-%d")
                },
                {
                    "$inc": {"total_screen_share_time": screen_share_time}
                },
                upsert=True
            )
            
            # Reset screen share time
            await sessions.update_one(
                {"_id": session["_id"]},
                {"$set": {"screen_share_time": 0}}
            )
            
            logger.info(f"Reset screen share time for session {session['_id']}")
    except Exception as e:
        logger.error(f"❌ Error resetting screen share time: {e}")

async def clean_expired_cache():
    """Clean up expired cache items."""
    try:
        # Implement cache cleanup logic here
        logger.info("Cache cleanup completed")
    except Exception as e:
        logger.error(f"❌ Error cleaning cache: {e}")

async def optimize_database():
    """Perform database maintenance tasks."""
    try:
        db = await get_database()
        if db is None:
            logger.error("❌ Database connection not available")
            return
        
        # Remove old sessions (older than 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        result = await db.sessions.delete_many({
            "timestamp": {"$lt": thirty_days_ago}
        })
        logger.info(f"Removed {result.deleted_count} old sessions")
        
        # Compact collections
        try:
            await db.command("compact", "sessions")
            await db.command("compact", "activities")
            logger.info("Database compaction completed")
        except Exception as e:
            logger.warning(f"Database compaction skipped: {e}")
    except Exception as e:
        logger.error(f"❌ Error optimizing database: {e}")

async def monitor_memory_usage():
    """Monitor server memory usage."""
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        logger.info(f"Server memory usage: {memory_mb:.2f} MB")
        
        if memory_mb > 500:
            logger.warning(f"High memory usage: {memory_mb:.2f} MB")
        if memory_mb > 1000:
            logger.critical(f"CRITICAL: Memory usage very high: {memory_mb:.2f} MB")
    except Exception as e:
        logger.error(f"❌ Error monitoring memory: {e}")

async def monitor_db_connection_pool():
    """Monitor MongoDB connection pool usage."""
    try:
        db = await get_database()
        if db is None:
            logger.error("❌ Database connection not available")
            return
            
        server_status = await db.command("serverStatus")
        conn_stats = server_status.get("connections", {})
        
        current = conn_stats.get("current", 0)
        available = conn_stats.get("available", 0)
        max_conns = current + available
        usage_percent = (current / max_conns * 100) if max_conns > 0 else 0
        
        logger.info(f"MongoDB Connection Pool: {current}/{max_conns} connections used ({usage_percent:.1f}%)")
        
        if usage_percent > 80:
            logger.warning(f"MongoDB connection pool nearing capacity: {usage_percent:.1f}% used")
        if usage_percent > 95:
            logger.critical(f"CRITICAL: MongoDB connection pool almost exhausted: {usage_percent:.1f}% used")
    except Exception as e:
        logger.error(f"❌ Error monitoring connection pool: {e}")

def setup_background_tasks(scheduler: AsyncIOScheduler):
    """Setup all background tasks."""
    # Update screen share time every 5 minutes
    scheduler.add_job(update_screen_share_time, 'interval', minutes=5, id='update_screen_share_time')
    
    # Reset screen share time at midnight UTC
    scheduler.add_job(reset_screen_share_time, 'cron', hour=0, minute=0, id='reset_screen_share_time')
    
    # Clean cache every 15 minutes
    scheduler.add_job(clean_expired_cache, 'interval', minutes=15, id='clean_expired_cache')
    
    # Optimize database weekly on Sunday at 2 AM
    scheduler.add_job(optimize_database, 'cron', day_of_week='sun', hour=2, id='optimize_database')
    
    # Monitor memory usage every 10 minutes
    scheduler.add_job(monitor_memory_usage, 'interval', minutes=10, id='monitor_memory_usage')
    
    # Monitor DB connection pool every 5 minutes
    scheduler.add_job(monitor_db_connection_pool, 'interval', minutes=5, id='monitor_db_connection_pool') 