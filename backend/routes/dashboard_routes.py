"""
Dashboard routes for handling dashboard-related API endpoints.
"""
import logging
import threading
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from bson import ObjectId
from services.user_service import user_service
from mongodb import sessions_collection, daily_summaries_collection, activities_collection
from utils.helpers import monitor_performance, gzip_response, serialize_mongodb_doc, ensure_timezone_aware, get_cached_data

logger = logging.getLogger(__name__)

# Create Blueprint
dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/api/dashboard', methods=['GET'])
@monitor_performance
@gzip_response
def get_dashboard():
    """Get dashboard data"""
    try:
        # Check if we have a cached version
        cache_key = "dashboard"
        
        # Get users with pagination support
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 100))
        
        # Define the query function for cache
        def query_func():
            skip = (page - 1) * per_page
            
            # Get total count for pagination info
            total_users = user_service.get_user_count()
            
            # Get users for current page
            users = user_service.get_users_paginated(skip, per_page)
            current_date = datetime.now(timezone.utc).date()
            
            # Process user data in parallel using threads
            dashboard_data = []
            threads = []
            results = [None] * len(users)
            
            def process_user(index, user):
                try:
                    results[index] = get_user_dashboard_data(user, current_date)
                except Exception as e:
                    logger.error(f"Error processing user {user.get('username')}: {e}")
                    results[index] = {
                        "username": user.get("username", "unknown"),
                        "display_name": user.get("display_name", user.get("username", "unknown")),
                        "error": str(e),
                        "active_apps": []  # Ensure active_apps is always an array
                    }
            
            # Create and start threads
            for i, user in enumerate(users):
                thread = threading.Thread(target=process_user, args=(i, user))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            # Collect results and filter out None values
            dashboard_data = [r for r in results if r is not None]
            
            # Ensure data is an array
            if not isinstance(dashboard_data, list):
                dashboard_data = []
            
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
        
        # Get data from cache or execute query
        dashboard_data = get_cached_data(cache_key, "users", query_func)
        
        return jsonify(dashboard_data)
    except Exception as e:
        logger.error(f"❌ Error in dashboard endpoint: {e}", exc_info=True)
        # Return a valid response even on error
        return jsonify({
            'error': str(e), 
            'status': 'error',
            'data': []  # Ensure data is always an array
        }), 500

def get_user_dashboard_data(user, current_date):
    """Get dashboard data for a specific user"""
    try:
        latest_session = get_latest_session(user)
        first_join, last_leave = get_day_sessions(user, current_date)
        total_session_hours = calculate_session_time(first_join, last_leave)
        app_usage, total_active_time, active_apps, most_active_app = get_app_usage(user, current_date)
        daily_summary = get_daily_summary(user, current_date)
        
        # Ensure timestamp is properly formatted if it exists
        timestamp = None
        if latest_session and latest_session.get("timestamp"):
            timestamp_dt = ensure_timezone_aware(latest_session.get("timestamp"))
            timestamp = timestamp_dt.isoformat()
        
        # Ensure duty start and end times are properly formatted
        duty_start_time = None
        if first_join and first_join.get("start_time"):
            start_time_dt = ensure_timezone_aware(first_join.get("start_time"))
            duty_start_time = start_time_dt.isoformat()
        
        duty_end_time = None
        if last_leave and last_leave.get("stop_time"):
            end_time_dt = ensure_timezone_aware(last_leave.get("stop_time"))
            duty_end_time = end_time_dt.isoformat()
        
        # Handle potential None values for most_active_app
        most_used_app = None
        most_used_app_time = 0
        if most_active_app:
            most_used_app = most_active_app.get("app_name")
            most_used_app_time = round(most_active_app.get("total_time", 0), 2)
        
        # Safely get daily summaries
        try:
            daily_summaries = list(daily_summaries_collection.find(
                {"user_id": user["_id"]},
                sort=[("date", -1)],
                limit=7
            ))
        except Exception:
            daily_summaries = []
        
        return {
            "username": user["username"],
            "display_name": user.get("display_name", user["username"]),
            "channel": latest_session.get("channel") if latest_session else None,
            "screen_shared": latest_session.get("screen_shared", False) if latest_session else False,
            "timestamp": timestamp,
            "active_app": most_used_app,
            "active_apps": active_apps or [],
            "screen_share_time": latest_session.get("screen_share_time", 0) if latest_session else 0,
            "total_idle_time": daily_summary.get("total_idle_time", 0) if daily_summary else 0,
            "total_active_time": total_active_time or 0,
            "total_session_time": total_session_hours or 0,
            "duty_start_time": duty_start_time,
            "duty_end_time": duty_end_time,
            "app_usage": app_usage or [],
            "most_used_app": most_used_app,
            "most_used_app_time": most_used_app_time,
            "daily_summaries": daily_summaries
        }
    except Exception as e:
        logger.error(f"Error in get_user_dashboard_data for user {user.get('username')}: {e}", exc_info=True)
        # Return minimal data to prevent frontend errors
        return {
            "username": user.get("username", "unknown"),
            "display_name": user.get("display_name", user.get("username", "unknown")),
            "error": str(e),
            "screen_shared": False,
            "channel": None,
            "timestamp": None,
            "active_app": None,
            "active_apps": [],
            "screen_share_time": 0,
            "total_idle_time": 0,
            "total_active_time": 0,
            "total_session_time": 0,
            "app_usage": [],
            "most_used_app": None,
            "most_used_app_time": 0,
            "daily_summaries": []
        }

def get_latest_session(user):
    """Get the latest session for a user"""
    return sessions_collection.find_one(
        {"user_id": user["_id"]},
        sort=[("timestamp", -1)]
    )

def get_day_sessions(user, current_date):
    """Get the first join and last leave sessions for a user on a specific date"""
    day_start = datetime.combine(current_date, datetime.min.time(), tzinfo=timezone.utc)
    day_end = datetime.combine(current_date, datetime.max.time(), tzinfo=timezone.utc)
    first_join = sessions_collection.find_one({
        "user_id": user["_id"],
        "event": "joined",
        "start_time": {"$gte": day_start, "$lte": day_end}
    }, sort=[("start_time", 1)])
    
    last_leave = sessions_collection.find_one({
        "user_id": user["_id"],
        "event": "left",
        "stop_time": {"$gte": day_start, "$lte": day_end}
    }, sort=[("stop_time", -1)])
    
    return first_join, last_leave

def calculate_session_time(first_join, last_leave):
    """Calculate session time in hours"""
    if first_join and last_leave and first_join.get("start_time") and last_leave.get("stop_time"):
        first_join_time = ensure_timezone_aware(first_join["start_time"])
        last_leave_time = ensure_timezone_aware(last_leave["stop_time"])
        
        if last_leave_time > first_join_time:
            total_session_seconds = (last_leave_time - first_join_time).total_seconds()
            # Convert to hours and round to 2 decimal places
            return round(total_session_seconds / 3600, 2)
        else:
            # Handle case where timestamps might be out of order
            logger.warning(f"⚠️ Warning: Last leave time ({last_leave_time}) is before first join time ({first_join_time})")
            return 0
    return 0

def get_app_usage(user, current_date):
    """Get app usage data for a user on a specific date"""
    day_str = current_date.strftime("%Y-%m-%d")
    activities_today = list(activities_collection.find({
        "user_id": user["_id"],
        "date": day_str
    }))
    
    # Ensure app_usage is always a list, even if empty
    app_usage = [
        {"app_name": a["app_name"], "total_time": max(a.get("total_time", 0), 0)}
        for a in activities_today
    ] if activities_today else []
    
    # Get total_active_time from daily_summary instead of calculating from activities
    daily_summary = daily_summaries_collection.find_one({
        "user_id": user["_id"],
        "date": day_str
    })
    
    # Use the stored total_active_time if available, otherwise calculate from activities
    if daily_summary and "total_active_time" in daily_summary:
        total_active_time = daily_summary["total_active_time"]
    else:
        total_active_time = round(sum(a.get("total_time", 0) for a in app_usage), 2)
    
    active_apps = [a["app_name"] for a in app_usage if a.get("total_time", 0) > 0]
    
    # Handle empty app_usage case
    if not app_usage:
        most_active_app = None
    else:
        try:
            most_active_app = max(app_usage, key=lambda x: x.get("total_time", 0), default=None)
        except (ValueError, TypeError):
            most_active_app = None
            
    return app_usage, total_active_time, active_apps, most_active_app

def get_daily_summary(user, current_date):
    """Get daily summary for a user on a specific date"""
    # Check if current_date is already a string or a datetime object
    if isinstance(current_date, str):
        day_str = current_date
    else:
        day_str = current_date.strftime("%Y-%m-%d")
    
    # Use projection to get only needed fields
    return daily_summaries_collection.find_one(
        {"user_id": user["_id"], "date": day_str},
        projection={"total_active_time": 1, "total_idle_time": 1, "app_summaries": 1, "_id": 1}
    )