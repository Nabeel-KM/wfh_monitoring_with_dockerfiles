from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone, timedelta
from ..services.mongodb import get_database
import logging

logger = logging.getLogger(__name__)

async def update_screen_share_time():
    """Update screen share time for active sessions."""
    try:
        logger.info("⏰ Running incremental screen share time update...")
        db = await get_database()
        if not db:
            logger.error("Database connection not available")
            return

        sessions = db.sessions
        # Fetch active screen sharing sessions
        active_sessions = await sessions.find({
            "screen_shared": True,
            "start_time": {"$ne": None}
        }).to_list(length=None)

        for session in active_sessions:
            user_id = session["user_id"]
            start_time = session["start_time"]
            current_time = datetime.now(timezone.utc)

            if start_time < current_time:
                elapsed_time = (current_time - start_time).total_seconds()
                logger.info(f"⏱ Incrementing screen share time by {elapsed_time} seconds for user_id: {user_id}")

                await sessions.update_one(
                    {"_id": session["_id"]},
                    {
                        "$inc": {"screen_share_time": int(elapsed_time)},
                        "$set": {"start_time": current_time, "timestamp": current_time}
                    }
                )
            else:
                logger.warning(f"⚠️ Invalid time calculation: start_time ({start_time}) is after current time ({current_time})")
                await sessions.update_one(
                    {"_id": session["_id"]},
                    {
                        "$set": {"start_time": current_time, "timestamp": current_time}
                    }
                )

        logger.info("✅ Incremental screen share time update completed.")
    except Exception as e:
        logger.error(f"❌ Error during incremental screen share time update: {e}")

async def reset_screen_share_time():
    """Reset screen share time and update daily summaries."""
    try:
        logger.info("⏰ Running daily reset task...")
        db = await get_database()
        if not db:
            logger.error("Database connection not available")
            return

        sessions = db.sessions
        activities = db.activities
        daily_summaries = db.daily_summaries

        # Get yesterday's date
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        # Get sessions with screen share time
        active_sessions = await sessions.find({
            "screen_share_time": {"$gt": 0}
        }).to_list(length=None)

        for session in active_sessions:
            user_id = session["user_id"]
            screen_share_time = session["screen_share_time"]

            # Get latest activity for idle time
            latest_activity = await activities.find_one(
                {"user_id": user_id},
                sort=[("timestamp", -1)]
            )

            total_idle_time = latest_activity.get("idle_time", "0 mins") if latest_activity else "0 mins"

            # Parse idle time
            idle_time_minutes = 0
            try:
                if isinstance(total_idle_time, (int, float)):
                    idle_time_minutes = float(total_idle_time)
                elif isinstance(total_idle_time, str):
                    if "mins" in total_idle_time:
                        idle_time_minutes = float(total_idle_time.split()[0])
                logger.info(f"📊 Parsed idle time: {idle_time_minutes} minutes")
            except Exception as e:
                logger.warning(f"⚠️ Error parsing idle time: {e}")

            # Update daily summary
            await daily_summaries.update_one(
                {"user_id": user_id, "date": str(yesterday)},
                {
                    "$inc": {"total_screen_share_time": screen_share_time},
                    "$set": {"total_idle_time": idle_time_minutes}
                },
                upsert=True
            )

            # Reset screen share time
            await sessions.update_one(
                {"_id": session["_id"]},
                {"$set": {"screen_share_time": 0}}
            )

        logger.info("✅ Daily reset task completed successfully.")
    except Exception as e:
        logger.error(f"❌ Error during daily reset task: {e}")

async def clean_expired_cache():
    """Clean expired items from cache."""
    try:
        logger.info("🧹 Running cache cleanup...")
        # Implement cache cleanup logic here
        logger.info("✅ Cache cleanup completed.")
    except Exception as e:
        logger.error(f"❌ Error during cache cleanup: {e}")

async def optimize_database():
    """Perform database maintenance tasks."""
    try:
        logger.info("🔧 Running database optimization...")
        db = await get_database()
        if not db:
            logger.error("Database connection not available")
            return

        # Remove old sessions (older than 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        result = await db.sessions.delete_many({
            "timestamp": {"$lt": thirty_days_ago}
        })
        logger.info(f"🗑️ Removed {result.deleted_count} old sessions")

        # Compact collections if possible
        try:
            await db.command("compact", "sessions")
            await db.command("compact", "activities")
            logger.info("✅ Database compaction completed")
        except Exception as e:
            logger.warning(f"⚠️ Database compaction skipped: {e}")

    except Exception as e:
        logger.error(f"❌ Error during database optimization: {e}")

async def cleanup_old_data():
    """Remove data older than 90 days."""
    try:
        logger.info("🧹 Running old data cleanup...")
        db = await get_database()
        if not db:
            logger.error("Database connection not available")
            return

        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
        await db.activities.delete_many({"date": {"$lt": cutoff_date}})
        await db.daily_summaries.delete_many({"date": {"$lt": cutoff_date}})
        logger.info(f"✅ Removed data older than {cutoff_date}")
    except Exception as e:
        logger.error(f"❌ Error during old data cleanup: {e}")

def setup_scheduler():
    """Set up the scheduler with all tasks."""
    scheduler = AsyncIOScheduler()

    # Add jobs
    scheduler.add_job(
        update_screen_share_time,
        IntervalTrigger(minutes=5),
        id='update_screen_share_time'
    )

    scheduler.add_job(
        reset_screen_share_time,
        CronTrigger(hour=0, minute=0),
        id='reset_screen_share_time'
    )

    scheduler.add_job(
        clean_expired_cache,
        IntervalTrigger(minutes=15),
        id='clean_expired_cache'
    )

    scheduler.add_job(
        optimize_database,
        CronTrigger(day_of_week='sun', hour=2),
        id='optimize_database'
    )

    scheduler.add_job(
        cleanup_old_data,
        CronTrigger(day_of_week='mon', hour=1),
        id='cleanup_old_data'
    )

    return scheduler 