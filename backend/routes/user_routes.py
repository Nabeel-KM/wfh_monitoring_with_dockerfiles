"""
User routes for handling user-related API endpoints.
"""
import logging
from flask import Blueprint, request, jsonify
from services.user_service import user_service
from utils.helpers import monitor_performance, gzip_response, serialize_mongodb_doc

logger = logging.getLogger(__name__)

# Create Blueprint
user_bp = Blueprint('user', __name__)

@user_bp.route('/api/users', methods=['GET'])
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

@user_bp.route('/api/users/active', methods=['GET'])
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

@user_bp.route('/api/users/<username>', methods=['GET'])
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

@user_bp.route('/api/users/<username>/status', methods=['GET'])
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