"""
Session routes for handling session-related API endpoints.
"""
import logging
from flask import Blueprint, request, jsonify
from services.user_service import user_service
from services.session_service import session_service
from utils.helpers import monitor_performance, gzip_response

logger = logging.getLogger(__name__)

# Create Blueprint
session_bp = Blueprint('session', __name__)

@session_bp.route('/api/session', methods=['POST'])
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

@session_bp.route('/api/sessions/<username>', methods=['GET'])
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