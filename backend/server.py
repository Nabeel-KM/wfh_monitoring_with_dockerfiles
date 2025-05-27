"""
Main application entry point.
"""
import logging
import time
import os
from logging.handlers import RotatingFileHandler
from config import create_app, scheduler
from mongodb import mongo_connection
from routes.user_routes import user_bp, users_bp
from routes.session_routes import session_bp, sessions_bp
from routes.activity_routes import activity_bp
from routes.screenshot_routes import screenshot_bp
from routes.dashboard_routes import dashboard_bp
from routes.history_routes import history_bp
from routes.stats_routes import stats_bp
from routes.health_routes import health_bp
from routes.missing_routes import missing_bp
from routes.report_routes import reports_bp
from flask import jsonify, Flask

# Configure logging
LOG_FORMAT = '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s'
LOG_FILE = 'logs/app.log'

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Increase logging for important modules
logging.getLogger('services').setLevel(logging.DEBUG)
logging.getLogger('routes').setLevel(logging.DEBUG)

# Create Flask app
app, limiter = create_app()

# Store app start time for uptime calculation
app.start_time = time.time()

# Register blueprints
app.register_blueprint(activity_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(sessions_bp)
app.register_blueprint(users_bp)
app.register_blueprint(user_bp)
app.register_blueprint(session_bp)
app.register_blueprint(screenshot_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(history_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(health_bp)
app.register_blueprint(missing_bp)

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return {'status': 'ok'}

# Start scheduler
@app.before_first_request
def start_scheduler():
    """Start the background scheduler"""
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Background scheduler started")

# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return {'error': 'Not found'}, 404

@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    logger.error(f"❌ Server error: {error}")
    return {'error': 'Internal server error'}, 500

# CORS headers
@app.after_request
def add_cors_headers(response):
    """Add CORS headers to all responses"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,Cache-Control'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    """Handle preflight OPTIONS requests"""
    response = jsonify({'status': 'ok'})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,Cache-Control'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

if __name__ == '__main__':
    # Ensure MongoDB connection is established
    try:
        mongo_connection.client.admin.command('ping')
        logger.info("✅ MongoDB connection successful")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        exit(1)
        
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)