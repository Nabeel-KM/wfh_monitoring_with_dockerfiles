"""
Main application entry point.
"""
import logging
from config import create_app, scheduler
from mongodb import mongo_connection
from routes.user_routes import user_bp
from routes.session_routes import session_bp
from routes.activity_routes import activity_bp
from routes.screenshot_routes import screenshot_bp
from routes.dashboard_routes import dashboard_bp
from routes.history_routes import history_bp

# Configure logging
logger = logging.getLogger(__name__)

# Create Flask app
app, limiter = create_app()

# Register blueprints
app.register_blueprint(user_bp)
app.register_blueprint(session_bp)
app.register_blueprint(activity_bp)
app.register_blueprint(screenshot_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(history_bp)

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