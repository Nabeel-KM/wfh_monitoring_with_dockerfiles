"""
Stats routes for handling stats-related API endpoints.
"""
import logging
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
from mongodb import users_collection, sessions_collection, activities_collection, daily_summaries_collection
from utils.helpers import monitor_performance, gzip_response, serialize_mongodb_doc
import time

logger = logging.getLogger(__name__)

# Create Blueprint
stats_bp = Blueprint('stats', __name__)

@stats_bp.route('/api/stats', methods=['GET'])
@monitor_performance
@gzip_response
def get_stats():
    """Get system statistics and metrics"""
    try:
        # Get collection stats
        users_count = users_collection.count_documents({})
        sessions_count = sessions_collection.count_documents({})
        activities_count = activities_collection.count_documents({})
        summaries_count = daily_summaries_collection.count_documents({})
        
        # Get active users (users with activity in the last 24 hours)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        active_users = len(list(daily_summaries_collection.distinct("user_id", {
            "last_updated": {"$gte": yesterday}
        })))
        
        # Get cache stats from global cache object
        from utils.helpers import cache
        cache_stats = {
            "users_cached": len(cache["users"]),
            "sessions_cached": len(cache["sessions"]),
            "summaries_cached": len(cache["summaries"]),
            "total_cached_items": len(cache["users"]) + len(cache["sessions"]) + len(cache["summaries"])
        }
        
        # Get top apps across all users for today
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pipeline = [
            {"$match": {"date": today}},
            {"$group": {"_id": "$app_name", "total_time": {"$sum": "$total_time"}}},
            {"$sort": {"total_time": -1}},
            {"$limit": 10}
        ]
        top_apps = list(activities_collection.aggregate(pipeline))
        
        # Get app start time from Flask app
        from flask import current_app
        uptime = time.time() - current_app.start_time if hasattr(current_app, 'start_time') else 0
        
        return jsonify({
            "database": {
                "users": users_count,
                "sessions": sessions_count,
                "activities": activities_count,
                "summaries": summaries_count,
                "active_users_24h": active_users
            },
            "cache": cache_stats,
            "top_apps_today": [{"app": app["_id"], "minutes": app["total_time"]} for app in top_apps],
            "server_time": datetime.now(timezone.utc).isoformat(),
            "uptime": uptime
        })
    except Exception as e:
        logger.error(f"❌ Error getting stats: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@stats_bp.route('/api/verify_data', methods=['GET'])
def verify_data():
    """Endpoint to verify data in collections"""
    try:
        username = request.args.get('username')
        if not username:
            return jsonify({'error': 'Username required'}), 400

        user = users_collection.find_one({"username": username})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Get today's date
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Get activities
        activities = list(activities_collection.find({
            "user_id": user["_id"],
            "date": today
        }))

        # Get daily summary
        daily_summary = daily_summaries_collection.find_one({
            "user_id": user["_id"],
            "date": today
        })

        return jsonify({
            'activities': [
                {
                    'app_name': a['app_name'],
                    'total_time': a['total_time'],
                    'last_updated': a['last_updated'].isoformat()
                } for a in activities
            ],
            'daily_summary': {
                'total_active_time': daily_summary['total_active_time'] if daily_summary else 0,
                'last_updated': daily_summary['last_updated'].isoformat() if daily_summary else None
            } if daily_summary else None
        })
    except Exception as e:
        logger.error(f"❌ Error verifying data: {e}")
        return jsonify({'error': str(e)}), 500

@stats_bp.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Clear the server cache"""
    try:
        import os
        # Check for admin token
        token = request.headers.get('Authorization')
        if not token or token != f"Bearer {os.getenv('ADMIN_TOKEN', 'admin')}":
            return jsonify({'error': 'Unauthorized'}), 401
            
        # Clear cache
        from utils.helpers import cache
        cache_size = len(cache["users"]) + len(cache["sessions"]) + len(cache["summaries"])
        cache["users"].clear()
        cache["sessions"].clear()
        cache["summaries"].clear()
        cache["last_updated"].clear()
        
        return jsonify({
            "success": True,
            "message": f"Cache cleared successfully. {cache_size} items removed.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.error(f"❌ Error clearing cache: {e}")
        return jsonify({'error': str(e)}), 500