"""
Routes for generating and retrieving various reports
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from services.user_service import user_service
from services.activity_service import activity_service
from utils.helpers import monitor_performance, gzip_response
from mongodb import activities_collection, users_collection

logger = logging.getLogger(__name__)

# Create Blueprint
reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/api/reports/activity', methods=['GET'])
@monitor_performance
@gzip_response
def get_activity_report():
    """Get detailed activity report for a user"""
    try:
        username = request.args.get('username')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not username:
            return jsonify({'error': 'Username is required'}), 400

        # Validate dates
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime.now(timezone.utc)
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else start_dt
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        user = user_service.get_user_by_username(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        activities = activity_service.get_user_activities(
            user["_id"], 
            start_dt.date(),
            end_dt.date()
        )

        report_data = {
            "username": username,
            "display_name": user.get("display_name", username),
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "end_date": end_dt.strftime("%Y-%m-%d"),
            "activities": activities
        }

        logger.info(f"✅ Generated activity report for {username}")
        return jsonify(report_data)

    except Exception as e:
        logger.error(f"❌ Error generating activity report: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500