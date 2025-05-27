"""
Routes for managing user sessions
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from services.user_service import user_service
from services.session_service import session_service
from utils.helpers import monitor_performance, gzip_response
from mongodb import sessions_collection

logger = logging.getLogger(__name__)

# Create Blueprint
sessions_bp = Blueprint('sessions', __name__)

@sessions_bp.route('/api/sessions/manage', methods=['POST'])
@monitor_performance
def manage_session():
    """Manage user sessions (manual start/stop)"""
    try:
        data = request.json
        username = data.get('username')
        action = data.get('action')
        
        if not username or not action:
            return jsonify({'error': 'Username and action are required'}), 400
            
        if action not in ['start', 'stop']:
            return jsonify({'error': 'Invalid action. Use start or stop'}), 400

        user = user_service.get_user_by_username(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        result = session_service.manage_user_session(user["_id"], action)
        
        logger.info(f"✅ Session {action} successful for {username}")
        return jsonify({'success': True, 'message': f'Session {action}ed'})

    except Exception as e:
        logger.error(f"❌ Error managing session: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@sessions_bp.route('/api/session', methods=['POST'])
@monitor_performance
def handle_session():
    """Handle session events (join, leave, start/stop streaming)"""
    data = request.json
    logger.info(f"✅ Received session data: {data}")

    try:
        validate_session_data(data)
        user_id = user_service.get_or_create_user(data['username'])
        
        # Update user's display_name if provided
        if 'display_name' in data and data['display_name']:
            user_service.update_user(user_id, {"display_name": data['display_name']})
            
        session_service.handle_session_event(user_id, data)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"❌ Error processing session: {e}")
        return jsonify({'error': str(e)}), 500

@sessions_bp.route('/api/sessions/<username>', methods=['GET'])
@monitor_performance
@gzip_response
def get_user_sessions(username):
    """Get sessions for a specific user"""
    try:
        limit = int(request.args.get('limit', 100))
        user = user_service.get_user_by_username(username)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        sessions = session_service.get_user_sessions(user['_id'], limit)
        
        return jsonify({
            'username': username,
            'sessions': sessions
        })
    except Exception as e:
        logger.error(f"❌ Error getting user sessions: {e}")
        return jsonify({'error': str(e)}), 500

def validate_session_data(data):
    """Validate session data"""
    required_fields = ['username', 'channel', 'screen_shared', 'event']
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        logger.error(f"❌ Missing fields: {missing_fields}")
        raise ValueError(f'Missing fields: {missing_fields}')

    event = data.get('event')
    if event not in ['joined', 'left', 'started_streaming', 'stopped_streaming']:
        logger.error(f"❌ Invalid event type: {event}")
        raise ValueError('Invalid event type')