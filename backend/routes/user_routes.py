"""
Routes for user management and settings
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from services.user_service import user_service
from utils.helpers import monitor_performance, gzip_response, serialize_mongodb_doc

logger = logging.getLogger(__name__)

# Create Blueprint
users_bp = Blueprint('users', __name__)

@users_bp.route('/api/users', methods=['GET'])
@monitor_performance
@gzip_response
def get_users():
    """Get all users"""
    try:
        users = user_service.get_all_users()
        return jsonify({
            'users': serialize_mongodb_doc(users)
        })
    except Exception as e:
        logger.error(f"❌ Error getting users: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/users/active', methods=['GET'])
@monitor_performance
@gzip_response
def get_active_users():
    """Get all active users"""
    try:
        users = user_service.get_active_users()
        return jsonify({
            'users': serialize_mongodb_doc(users)
        })
    except Exception as e:
        logger.error(f"❌ Error getting active users: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/users/<username>', methods=['GET'])
@monitor_performance
@gzip_response
def get_user(username):
    """Get user by username"""
    try:
        user = user_service.get_user_by_username(username)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        return jsonify({
            'user': serialize_mongodb_doc(user)
        })
    except Exception as e:
        logger.error(f"❌ Error getting user: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/users/<username>/status', methods=['GET'])
@monitor_performance
def get_user_status(username):
    """Get user's current status"""
    try:
        user = user_service.get_user_by_username(username)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        status = user_service.get_user_session_status(user['_id'])
        
        return jsonify({
            'username': username,
            'status': status
        })
    except Exception as e:
        logger.error(f"❌ Error getting user status: {e}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/api/session_status', methods=['GET'])
@monitor_performance
def session_status():
    """Get session status for a user"""
    try:
        username = request.args.get('username')
        if not username:
            return jsonify({'error': 'Username required'}), 400

        user = user_service.get_user_by_username(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Get latest session
        latest_session = user_service.get_latest_session(user["_id"])

        # Ensure we return a valid response even if session is None
        return jsonify({
            "username": user["username"],
            "display_name": user.get("display_name", user["username"]),
            "screen_shared": latest_session.get("screen_shared", False) if latest_session else False,
            "channel": latest_session.get("channel", None) if latest_session else None,
            "timestamp": latest_session.get("timestamp", None) if latest_session else None,
            "active_app": latest_session.get("active_app", None) if latest_session else None,
            "active_apps": latest_session.get("active_apps", []) if latest_session else []
        })
    except Exception as e:
        logger.error(f"Error in session status: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500

@users_bp.route('/api/users/settings', methods=['GET', 'POST'])
@monitor_performance
def user_settings():
    """Get or update user settings"""
    try:
        username = request.args.get('username') or request.json.get('username')
        if not username:
            return jsonify({'error': 'Username is required'}), 400

        user = user_service.get_user_by_username(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if request.method == 'GET':
            settings = user_service.get_user_settings(user["_id"])
            logger.info(f"✅ Retrieved settings for user {username}")
            return jsonify(settings)
        else:
            data = request.json
            updated = user_service.update_user_settings(user["_id"], data)
            logger.info(f"✅ Updated settings for user {username}")
            return jsonify({'success': True, 'message': 'Settings updated'})

    except Exception as e:
        logger.error(f"❌ Error managing user settings: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500