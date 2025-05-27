"""
Configuration module for the application.
Contains all configuration settings and environment variables.
"""
import os
import logging
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
S3_BUCKET = os.getenv('S3_BUCKET', 'km-wfh-monitoring-bucket')

# Cache Configuration
CACHE_TTL = 60  # 1 minute

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Increase maximum content length to 50MB
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB in bytes
    app.config['JSON_SORT_KEYS'] = False  # Preserve key order in JSON responses
    
    # Configure CORS with proper settings
    CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["Content-Type", "Authorization", "Cache-Control"]}}, 
         supports_credentials=True)
    
    # Configure rate limiting - high limits for multiple users
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["10000 per day", "2000 per hour"]
    )
    
    return app, limiter

# Create scheduler for background tasks
scheduler = BackgroundScheduler()