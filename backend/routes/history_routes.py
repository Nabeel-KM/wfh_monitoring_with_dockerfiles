"""
History routes for handling history-related API endpoints.
"""
import logging
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
from bson import ObjectId
from services.user_service import user_service
from services.activity_service import activity_service
from mongodb import sessions_collection, daily_summaries_collection, activities_collection
from utils.helpers import monitor_performance, gzip_response, serialize_mongodb_doc, ensure_timezone_aware, get_cached_data

logger = logging.getLogger(__name__)

# Create Blueprint
history_bp = Blueprint('history', __name__)

@history_bp.route('/api/history', methods=['GET'])
@monitor_performance
@gzip_response
def get_history():
    """Get user history data"""
    try:
        username = request.args.get('username')
        days = int(request.args.get('days', 30))
        
        # Generate cache key based on parameters
        cache_key = f"history:{username}:{days}"
        
        # Try to get from cache first
        def query_func():
            users = get_users(username)
            if not users or not isinstance(users, list):
                return {'error': 'No users found', 'data': []}
                
            start_date, end_date = calculate_date_range(days)
            sessions_data = get_sessions_data(users, start_date, end_date)
            history_data = process_user_history(users, days, start_date, sessions_data)
            
            # Ensure history_data is always a list
            if not isinstance(history_data, list):
                history_data = []
                
            return history_data
        
        history_data = get_cached_data(cache_key, "summaries", query_func)
        
        return jsonify(history_data)
    except ValueError as ve:
        # Handle specific value errors like user not found
        logger.warning(f"Value error in history endpoint: {ve}")
        return jsonify({'error': str(ve), 'data': []}), 404
    except Exception as e:
        logger.error(f"❌ Error in history endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e), 'data': []}), 500

def get_users(username):
    if username:
        user = user_service.get_user_by_username(username)
        if not user:
            # Don't return a response object here, raise an exception instead
            raise ValueError(f'User not found: {username}')
        return [user]
    return user_service.get_all_users()

def calculate_date_range(days):
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days-1)
    return start_date, end_date

def get_sessions_data(users, start_date, end_date):
    # Convert date objects to datetime objects for MongoDB compatibility
    start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    pipeline = [
        {"$match": {
            "user_id": {"$in": [user["_id"] for user in users]},
            "$or": [
                {"start_time": {"$gte": start_datetime, "$lte": end_datetime}},
                {"stop_time": {"$gte": start_datetime, "$lte": end_datetime}}
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
    return list(sessions_collection.aggregate(pipeline))

def process_user_history(users, days, start_date, sessions_data):
    history_data = []
    
    # Ensure users is a list
    if not isinstance(users, list):
        logger.warning("process_user_history received non-list users parameter")
        return []
        
    for user in users:
        try:
            # Ensure user is a dictionary with required fields
            if not isinstance(user, dict) or "_id" not in user or "username" not in user:
                logger.warning(f"Invalid user object: {user}")
                continue
                
            user_history = {
                "username": user["username"], 
                "display_name": user.get("display_name", user["username"]),
                "days": []
            }
            
            for i in range(days):
                day = start_date + timedelta(days=i)
                day_str = day.strftime("%Y-%m-%d")
                session_data = get_session_data(user["_id"], day_str, sessions_data)
                daily_data = get_daily_data(user["_id"], day_str, session_data)
                
                # Ensure daily_data is valid
                if daily_data:
                    user_history["days"].append(daily_data)
                else:
                    # Add empty day data if none was returned
                    user_history["days"].append({
                        "date": day_str,
                        "first_activity": None,
                        "last_activity": None,
                        "total_session_time": 0,
                        "total_active_time": 0,
                        "total_idle_time": 0,
                        "app_usage": [],
                        "most_used_app": None,
                        "most_used_app_time": 0
                    })
            
            history_data.append(user_history)
        except Exception as e:
            logger.error(f"Error processing history for user {user.get('username', 'unknown')}: {e}")
            # Add a minimal user history object with empty days
            history_data.append({
                "username": user.get("username", "unknown"),
                "display_name": user.get("display_name", user.get("username", "unknown")),
                "error": str(e),
                "days": []
            })
            
    return history_data

def get_session_data(user_id, day_str, sessions_data):
    return next((s for s in sessions_data if s["_id"]["user_id"] == user_id and s["_id"]["date"] == day_str), None)

def get_daily_data(user_id, day_str, session_data):
    first_join_time, last_leave_time, total_session_hours = process_session_data(session_data)
    activities = get_activities(user_id, day_str)
    app_usage, most_active_app = process_activities(activities)
    
    # Get daily summary directly from collection
    daily_summary = daily_summaries_collection.find_one({
        "user_id": user_id,
        "date": day_str
    })
    
    return create_daily_data(day_str, first_join_time, last_leave_time, total_session_hours, app_usage, most_active_app, daily_summary)

def process_session_data(session_data):
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
    
    return first_join_time, last_leave_time, total_session_hours

def get_activities(user_id, day_str):
    return list(activities_collection.find({
        "user_id": user_id,
        "date": day_str
    }))

def process_activities(activities):
    # Ensure app_usage is always a list, even if empty
    app_usage = [
        {"app_name": a["app_name"], "total_time": max(a.get("total_time", 0), 0)}
        for a in activities
    ] if activities else []
    
    # Handle empty app_usage case
    if not app_usage:
        most_active_app = None
    else:
        try:
            most_active_app = max(app_usage, key=lambda x: x.get("total_time", 0), default=None)
        except (ValueError, TypeError):
            most_active_app = None
            
    return app_usage, most_active_app

def create_daily_data(day_str, first_join_time, last_leave_time, total_session_hours, app_usage, most_active_app, daily_summary):
    try:
        # Handle datetime objects properly
        if first_join_time:
            if isinstance(first_join_time, str):
                first_activity = first_join_time
            else:
                first_activity = first_join_time.isoformat()
        else:
            first_activity = None
            
        if last_leave_time:
            if isinstance(last_leave_time, str):
                last_activity = last_leave_time
            else:
                last_activity = last_leave_time.isoformat()
        else:
            last_activity = None
        
        # Convert active time from minutes to hours
        active_time = 0
        if daily_summary and "total_active_time" in daily_summary:
            # Convert minutes to hours (divide by 60)
            active_time = round(daily_summary.get("total_active_time", 0) / 60, 2)
        
        # Ensure app_usage is a list
        if not isinstance(app_usage, list):
            app_usage = []
        
        # Convert app usage times from minutes to hours
        normalized_app_usage = []
        for app in app_usage:
            if isinstance(app, dict) and "app_name" in app and "total_time" in app:
                normalized_app_usage.append({
                    "app_name": app["app_name"],
                    "total_time": round(app["total_time"] / 60, 2)  # Convert minutes to hours
                })
        
        # Convert most active app time from minutes to hours
        most_used_app = None
        most_used_app_time = 0
        if most_active_app and isinstance(most_active_app, dict):
            if "app_name" in most_active_app:
                most_used_app = most_active_app["app_name"]
            if "total_time" in most_active_app:
                most_used_app_time = round(most_active_app["total_time"] / 60, 2)
        
        # Convert idle time from minutes to hours if it exists
        idle_time = 0
        if daily_summary and "total_idle_time" in daily_summary:
            # Convert minutes to hours (divide by 60)
            idle_time = round(daily_summary.get("total_idle_time", 0) / 60, 2)
        
        return {
            "date": day_str,
            "first_activity": first_activity,
            "last_activity": last_activity,
            "total_session_time": total_session_hours or 0,
            "total_active_time": active_time,
            "total_idle_time": idle_time,
            "app_usage": normalized_app_usage,
            "most_used_app": most_used_app,
            "most_used_app_time": most_used_app_time
        }
    except Exception as e:
        logger.error(f"Error creating daily data for {day_str}: {e}")
        # Return a minimal valid object
        return {
            "date": day_str,
            "first_activity": None,
            "last_activity": None,
            "total_session_time": 0,
            "total_active_time": 0,
            "total_idle_time": 0,
            "app_usage": [],
            "most_used_app": None,
            "most_used_app_time": 0
        }