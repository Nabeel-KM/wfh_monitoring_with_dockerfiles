"""
Screenshot routes for handling screenshot-related API endpoints.
"""
import logging
import base64
from flask import Blueprint, request, jsonify
from services.user_service import user_service
from services.s3_service import s3_service
from utils.helpers import monitor_performance

logger = logging.getLogger(__name__)

# Create Blueprint
screenshot_bp = Blueprint('screenshot', __name__)

@screenshot_bp.route('/api/screenshot', methods=['POST'])
@monitor_performance
def upload_screenshot():
    """Upload a screenshot"""
    try:
        data = request.json
        
        if not data or 'username' not in data or 'image' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
            
        username = data['username']
        image_data = data['image']
        
        # Remove data URL prefix if present
        if image_data.startswith('data:image/png;base64,'):
            image_data = image_data[len('data:image/png;base64,'):]
            
        # Decode base64 image
        try:
            image_bytes = base64.b64decode(image_data)
        except Exception as e:
            logger.error(f"❌ Error decoding base64 image: {e}")
            return jsonify({'error': 'Invalid image data'}), 400
            
        # Get user
        user = user_service.get_user_by_username(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        # Generate object key
        import time
        timestamp = int(time.time())
        object_key = f"screenshots/{username}/{timestamp}.png"
        
        # Upload to S3
        success = s3_service.upload_file(image_bytes, object_key)
        
        if not success:
            return jsonify({'error': 'Failed to upload screenshot'}), 500
            
        # Get the URL
        url = s3_service.get_file_url(object_key)
        
        return jsonify({
            'ok': True,
            'url': url
        })
    except Exception as e:
        logger.error(f"❌ Error uploading screenshot: {e}")
        return jsonify({'error': str(e)}), 500

@screenshot_bp.route('/api/screenshots/<username>', methods=['GET'])
@monitor_performance
def get_screenshots(username):
    """Get screenshots for a user"""
    try:
        # Get user
        user = user_service.get_user_by_username(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        # List screenshots
        prefix = f"screenshots/{username}/"
        keys = s3_service.list_files(prefix)
        
        # Generate URLs
        screenshots = []
        for key in keys:
            url = s3_service.get_file_url(key)
            timestamp = key.split('/')[-1].split('.')[0]
            screenshots.append({
                'key': key,
                'url': url,
                'timestamp': timestamp
            })
            
        return jsonify({
            'username': username,
            'screenshots': screenshots
        })
    except Exception as e:
        logger.error(f"❌ Error getting screenshots: {e}")
        return jsonify({'error': str(e)}), 500