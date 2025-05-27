"""
Activity routes for handling activity-related API endpoints.
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from services.user_service import user_service
from services.activity_service import activity_service
from utils.helpers import monitor_performance, gzip_response

logger = logging.getLogger(__name__)

# Create Blueprint
activity_bp = Blueprint('activity', __name__)

@activity_bp.route('/api/activity', methods=['POST'])
@monitor_performance
def record_activity():
    """Record user activity"""
    data = request.json
    logger.info(f"✅ Received activity data: {data}")

    try:
        validate_activity_data(data)
        user_id = user_service.get_or_create_user(data['username'])
        
        # Update user's last active timestamp
        user_service.update_user_activity(user_id)
        
        # Record the activity
        activity_service.record_activity(user_id, data)
        
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"❌ Error recording activity: {e}")
        return jsonify({'error': str(e)}), 500

@activity_bp.route('/api/activities/<username>', methods=['GET'])
@monitor_performance
@gzip_response
def get_user_activities(username):
    """Get activities for a specific user"""
    try:
        limit = int(request.args.get('limit', 100))
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        
        user = user_service.get_user_by_username(username)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        activities = activity_service.get_user_activities(user['_id'], start_date, end_date, limit)
        
        return jsonify({
            'username': username,
            'activities': activities
        })
    except Exception as e:
        logger.error(f"❌ Error getting user activities: {e}")
        return jsonify({'error': str(e)}), 500

@activity_bp.route('/api/app-usage/<username>', methods=['GET'])
@monitor_performance
@gzip_response
def get_app_usage(username):
    """Get app usage statistics for a user"""
    try:
        date_str = request.args.get('date')
        date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        
        user = user_service.get_user_by_username(username)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        app_usage = activity_service.get_app_usage(user['_id'], date)
        
        return jsonify({
            'username': username,
            'app_usage': app_usage
        })
    except Exception as e:
        logger.error(f"❌ Error getting app usage: {e}")
        return jsonify({'error': str(e)}), 500

@activity_bp.route('/api/daily-summary/<username>', methods=['GET'])
@monitor_performance
@gzip_response
def get_daily_summary(username):
    """Get daily summary for a user"""
    try:
        date_str = request.args.get('date')
        date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        
        user = user_service.get_user_by_username(username)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        summary = activity_service.get_daily_summary(user['_id'], date)
        
        if not summary:
            return jsonify({
                'username': username,
                'summary': None
            })
        
        return jsonify({
            'username': username,
            'summary': summary
        })
    except Exception as e:
        logger.error(f"❌ Error getting daily summary: {e}")
        return jsonify({'error': str(e)}), 500

def validate_activity_data(data):
    """Validate activity data"""
    required_fields = ['username']
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        logger.error(f"❌ Missing fields: {missing_fields}")
        raise ValueError(f'Missing fields: {missing_fields}')