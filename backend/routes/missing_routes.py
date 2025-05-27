"""
Missing routes from the original server-old.py that need to be added to the refactored codebase.
"""
import logging
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from services.user_service import user_service
from services.activity_service import activity_service
from utils.helpers import monitor_performance, gzip_response

logger = logging.getLogger(__name__)

# Create Blueprint
missing_bp = Blueprint('missing', __name__)

@missing_bp.route('/api/activity/update_total_time', methods=['POST'])
@monitor_performance
def update_total_active_time():
    """Endpoint to directly update the total_active_time field for a user"""
    try:
        data = request.json
        username = data.get('username')
        date = data.get('date')
        total_active_time = data.get('total_active_time')
        
        if not username or not date or total_active_time is None:
            return jsonify({'error': 'Username, date, and total_active_time are required'}), 400
            
        # Get the user
        user = user_service.get_user_by_username(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        # Update the total_active_time
        result = activity_service.update_total_active_time(user['_id'], date, total_active_time)
        
        logger.info(f"✅ Incrementing total_active_time for {username} on {date} by {total_active_time}")
        return jsonify({'success': True, 'updated': result})
        
    except Exception as e:
        logger.error(f"❌ Error updating total_active_time: {e}")
        return jsonify({'error': str(e)}), 500

@missing_bp.route('/api/metrics', methods=['GET'])
@monitor_performance
@gzip_response
def get_metrics():
    """Get detailed metrics for a user"""
    try:
        username = request.args.get('username')
        date_str = request.args.get('date', datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        
        if not username:
            return jsonify({'error': 'Username required'}), 400
            
        # Generate cache key based on parameters
        cache_key = f"metrics:{username}:{date_str}"
        
        # Get user
        user = user_service.get_user_by_username(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        # Parse date
        try:
            current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
            
        # Calculate metrics
        metrics = activity_service.calculate_productivity_metrics(user, current_date)
        
        # Add user info
        metrics["username"] = user["username"]
        metrics["display_name"] = user.get("display_name", user["username"])
        metrics["date"] = date_str
        
        return jsonify(metrics)
        
    except Exception as e:
        logger.error(f"❌ Error getting metrics: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500