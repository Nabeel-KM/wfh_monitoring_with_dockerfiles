import psutil
import requests
import time
import subprocess
import json
import os
import sys
from pynput import mouse, keyboard
from datetime import datetime, timedelta, date
import hashlib
import logging
import boto3
from PIL import ImageGrab
import io
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import logging.handlers

# Load environment variables
load_dotenv()

# Add after imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.expanduser('~/.wfh-tracker/logs/tracker.log')
CACHE_FILE = os.path.expanduser('~/.wfh-tracker/cache/activity_cache.json')
AGGREGATED_LOG_FILE = os.path.expanduser('~/.wfh-tracker/logs/aggregated_log.json')
LAST_SYNC_FILE = os.path.expanduser('~/.wfh-tracker/cache/last_sync.json')

# Constants
API = os.getenv('API_URL', 'https://api-wfh.kryptomind.net/api/activity')
SESSION_STATUS_API = os.getenv('SESSION_STATUS_API', 'https://api-wfh.kryptomind.net/api/session_status')
USER = os.getenv('USER_ID', 'default_user')
IDLE_THRESHOLD = int(os.getenv('IDLE_THRESHOLD', '300'))  # 5 minutes
SYNC_INTERVAL = int(os.getenv('SYNC_INTERVAL', '1800'))  # 30 minutes
LOG_INTERVAL = int(os.getenv('LOG_INTERVAL', '60'))  # 1 minute
STATUS_CHECK_INTERVAL = int(os.getenv('STATUS_CHECK_INTERVAL', '30'))  # 30 seconds
SECONDS_TO_MINUTES = 60
SECONDS_TO_HOURS = 3600

# S3 Configuration
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
SCREENSHOT_INTERVAL = int(os.getenv('SCREENSHOT_INTERVAL', '1800'))  # 30 minutes in seconds

# Global variables
last_input = time.time()
last_sync_time = time.time()
last_log_time = time.time()
last_status_check_time = time.time()
app_usage = {}
tracking_enabled = False
last_screenshot_time = time.time()
has_joined_today = False
last_join_date = None


def ensure_directories():
    """Create necessary directories if they don't exist"""
    try:
        # Create logs directory
        log_dir = os.path.join(BASE_DIR, 'logs')
        cache_dir = os.path.join(BASE_DIR, 'cache')
        
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)
        
        # Create and set permissions for log file
        if not os.path.exists(LOG_FILE):
            open(LOG_FILE, 'a').close()
        os.chmod(LOG_FILE, 0o666)
        
        print("✅ Directory structure created successfully")
    except Exception as e:
        print(f"❌ Error creating directories: {e}")
        sys.exit(1)


def setup_logging():
    """Configure logging settings"""
    try:
        # Remove any existing handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        # Create logs directory if it doesn't exist
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

        # Use TimedRotatingFileHandler: rotate every day, keep 7 days
        try:
            file_handler = logging.handlers.TimedRotatingFileHandler(
                LOG_FILE, when='midnight', backupCount=7, encoding='utf-8'
            )
            file_handler.setLevel(logging.INFO)
            file_formatter = logging.Formatter(
                '[%(asctime)s] %(levelname)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
        except Exception as fe:
            print(f"❌ Error creating file handler: {fe}")
            file_handler = None

        # Configure console logging
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)

        # Setup root logger
        logging.root.setLevel(logging.INFO)
        if file_handler:
            logging.root.addHandler(file_handler)
        logging.root.addHandler(console_handler)

        # Test logging
        logging.info("✅ Logging system initialized")

    except Exception as e:
        print(f"❌ Error setting up logging: {e}")
        sys.exit(1)


# Move initialization calls after function definitions
ensure_directories()
setup_logging()

# Test logging immediately
logging.info("🚀 Tracker starting up...")


def log_message(message):
    """Log messages both to file and console"""
    logging.info(message)


def hash_username(username):
    return hashlib.sha256(username.encode()).hexdigest()


def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        subprocess.run(['xdotool', '--version'], capture_output=True)
    except FileNotFoundError:
        log_message("❌ Error: xdotool is not installed. Please install it using: sudo apt-get install xdotool")
        sys.exit(1)


# Check dependencies on startup
check_dependencies()


def on_activity(*args):
    """Handle any user activity event
    
    Args:
        *args: Variable arguments passed by the event listeners
    """
    global last_input
    last_input = time.time()


def setup_input_listeners():
    """Setup mouse and keyboard event listeners"""
    try:
        # Mouse listener
        mouse_listener = mouse.Listener(
            on_move=on_activity,
            on_click=on_activity,
            on_scroll=on_activity
        )
        mouse_listener.start()
        log_message("🖱️ Mouse listener initialized")

        # Keyboard listener
        keyboard_listener = keyboard.Listener(
            on_press=on_activity,
            on_release=on_activity
        )
        keyboard_listener.start()
        log_message("⌨️ Keyboard listener initialized")

    except Exception as e:
        log_message(f"❌ Error setting up input listeners: {str(e)}")
        raise e

    log_message("✅ Input listeners initialized")


def get_active_app_name():
    """Get the name of the currently active application."""
    try:
        # Get active window ID
        cmd = "xdotool getactivewindow getwindowname"
        window_name = subprocess.check_output(cmd.split()).decode().strip()
        
        cmd = "xdotool getactivewindow getwindowpid"
        pid = subprocess.check_output(cmd.split()).decode().strip()
        
        process = psutil.Process(int(pid))
        app_name = process.name()
        
        # Only log when window changes
        if hasattr(get_active_app_name, 'last_app') and get_active_app_name.last_app != app_name:
            log_message(f"🔄 Window changed: {app_name} ({window_name})")
        get_active_app_name.last_app = app_name
        
        return app_name
    except Exception as e:
        log_message(f"⚠️ Could not detect active window: {str(e)}")
        return None


def aggregate_app_usage(active_app, duration):
    """Aggregate the time spent on each app."""
    global app_usage
    if active_app not in app_usage:
        app_usage[active_app] = 0
    app_usage[active_app] += duration


def save_to_cache(data):
    try:
        existing_cache = []
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                existing_cache = json.load(f)
        
        existing_cache.append(data)
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(existing_cache, f)
        log_message("✅ Data cached successfully")
    except Exception as e:
        log_message(f"❌ Error saving to cache: {e}")


def send_cached_data():
    if not tracking_enabled or not has_joined_today:
        log_message("🔒 Not sending cached data (user not in wfh-monitoring channel or never joined today)")
        return
    if not os.path.exists(CACHE_FILE):
        return
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)
    if not cache:
        return
    # Only send the last (most recent) cached entry
    last_data = cache[-1]
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(API, json=last_data, headers=headers, timeout=10)
        log_message(f"✅ Sent latest cached data: {last_data}")
        log_message(f"📡 Response status: {response.status_code}")
        log_message(f"📡 Response body: {response.text}")
    except Exception as e:
        log_message(f"❌ Error sending cached data: {e}")
        return  # Keep cache for next time
    # Clear the cache after sending
    os.remove(CACHE_FILE)


def load_last_sync():
    if os.path.exists(LAST_SYNC_FILE):
        with open(LAST_SYNC_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_last_sync(last_sync):
    with open(LAST_SYNC_FILE, 'w') as f:
        json.dump(last_sync, f)


def sync_data():
    """Sync aggregated app usage data with the backend."""
    global app_usage
    
    if not app_usage:
        log_message("ℹ️ No data to sync")
        return
        
    current_time = datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")
    current_date = current_time.strftime("%Y-%m-%d")
    
    # Convert seconds to minutes before sending
    normalized_app_usage = {
        app: round(seconds / SECONDS_TO_MINUTES, 2)  # Convert to minutes with 2 decimal places
        for app, seconds in app_usage.items()
    }
    
    # Add per-app last_sync info
    app_sync_info = {}
    for app in normalized_app_usage:
        app_sync_info[app] = formatted_time

    data = {
        'username': USER,
        'app_usage': normalized_app_usage,
        'timestamp': formatted_time,
        'date': current_date,
        'app_sync_info': app_sync_info
    }
    
    log_message(f"📤 Attempting to sync data to {API}")
    log_message(f"📦 Payload: {json.dumps(data, indent=2)}")
    
    if tracking_enabled:
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(API, json=data, headers=headers, timeout=10)
            log_message(f"📡 Response status: {response.status_code}")
            log_message(f"📡 Response body: {response.text}")
            
            if response.status_code == 200:
                log_message("✅ Data synced successfully")
                app_usage = {}  # Reset after successful sync
                last_sync = load_last_sync()
                last_sync.update(app_sync_info)
                save_last_sync(last_sync)
            else:
                log_message(f"❌ Failed to sync data: {response.status_code}")
                save_to_cache(data)
        except requests.exceptions.RequestException as e:
            log_message(f"❌ Error syncing data: {str(e)}")
            save_to_cache(data)
    else:
        log_message("🔒 Not sending data to backend (user not in wfh-monitoring channel)")
        if has_joined_today:
            save_to_cache(data)
        else:
            log_message("🗒️ Not caching data: user has not joined the channel today")


def log_aggregated_data():
    """Log aggregated app usage data to the log file."""
    global app_usage
    if app_usage:
        log_message("📊 Activity Summary:")
        for app, duration in app_usage.items():
            log_message(f"   • {app}: {duration} seconds")
            if duration >= 60:
                minutes = duration // 60
                seconds = duration % 60
                log_message(f"     ({minutes}m {seconds}s)")
    else:
        log_message("💤 No activity recorded in this interval")


def check_session_status():
    """Check the user's session status using the backend API."""
    global tracking_enabled, has_joined_today, last_join_date
    try:
        log_message(f"🔍 Checking session status for user: {USER}")
        response = requests.get(f"{SESSION_STATUS_API}?username={USER}", timeout=5)
        log_message(f"📡 Session status response: {response.status_code}")
        
        if response.status_code == 200:
            session_status = response.json()
            log_message(f"📊 Session data: {json.dumps(session_status)}")
            
            # Check for channel joined status
            is_in_channel = session_status.get('channel') == 'wfh-monitoring'
            today = date.today().isoformat()
            if is_in_channel:
                if not has_joined_today or last_join_date != today:
                    has_joined_today = True
                    last_join_date = today
                if not tracking_enabled:
                    log_message(f"✅ User joined the channel. Starting tracking.")
                    tracking_enabled = True
                    send_cached_data()
            elif tracking_enabled:
                log_message(f"⏹️ User left the channel. Stopping tracking.")
                sync_data()
                tracking_enabled = False
                
        else:
            log_message(f"❌ Failed to fetch session status: {response.status_code}")
            log_message(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Error checking session status: {e}")
        time.sleep(5)


def initialize_s3_client():
    """Initialize and return an S3 client if credentials are available"""
    if not all([AWS_ACCESS_KEY, AWS_SECRET_KEY, S3_BUCKET_NAME]):
        log_message("⚠️ S3 credentials not configured. Screenshot uploads will be disabled.")
        return None
        
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            region_name=AWS_REGION
        )
        log_message("✅ S3 client initialized successfully")
        return s3_client
    except Exception as e:
        log_message(f"❌ Error initializing S3 client: {str(e)}")
        return None


def take_screenshot():
    """Capture screenshot and return as bytes"""
    try:
        log_message("📸 Taking screenshot...")
        screenshot = ImageGrab.grab()
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        log_message("✅ Screenshot captured successfully")
        return img_byte_arr
    except Exception as e:
        log_message(f"❌ Error taking screenshot: {e}")
        return None


def upload_screenshot_to_s3(s3_client, screenshot_bytes):
    """Upload screenshot to S3 bucket"""
    try:
        if not screenshot_bytes:
            log_message("⚠️ No screenshot data to upload")
            return False

        current_time = datetime.now()
        date_folder = current_time.strftime("%Y-%m-%d")
        time_str = current_time.strftime("%H-%M-%S")
        
        # Create S3 path: bucket/username/date/screenshot-time.png
        s3_path = f"{USER}/{date_folder}/screenshot-{time_str}.png"
        
        log_message(f"📤 Uploading screenshot to S3: {s3_path}")
        
        s3_client.upload_fileobj(
            screenshot_bytes,
            S3_BUCKET_NAME,
            s3_path,
            ExtraArgs={
                'ContentType': 'image/png',
                'ACL': 'private'
            }
        )
        
        log_message(f"📸 Screenshot uploaded to S3: {s3_path}")
        return True
    except Exception as e:
        log_message(f"❌ Error uploading screenshot to S3: {e}")
        log_message(f"Error details: {str(e)}")
        return False


def take_and_upload_screenshot(s3_client):
    """Take screenshot and upload to S3"""
    try:
        # Take screenshot
        log_message("📸 Taking screenshot...")
        screenshot = ImageGrab.grab()
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)

        # Generate S3 path
        current_time = datetime.now()
        date_folder = current_time.strftime("%Y-%m-%d")
        time_str = current_time.strftime("%H-%M-%S")
        s3_path = f"{USER}/{date_folder}/screenshot-{time_str}.png"

        # Upload to S3
        log_message(f"📤 Uploading screenshot to: {s3_path}")
        s3_client.upload_fileobj(
            img_byte_arr,
            S3_BUCKET_NAME,
            s3_path,
            ExtraArgs={'ContentType': 'image/png'}
        )
        log_message("✅ Screenshot uploaded successfully")
        return True
    except Exception as e:
        log_message(f"❌ Error in screenshot process: {str(e)}")
        return False


def main_loop():
    """Main tracking loop"""
    global last_input, last_sync_time, last_log_time, last_status_check_time, app_usage, last_screenshot_time, has_joined_today, last_join_date
    
    log_message("✅ Starting tracker...")
    setup_input_listeners()
    send_cached_data()
    
    # Initialize S3 client with retry
    retry_count = 0
    s3_client = None
    while retry_count < 3 and not s3_client:
        s3_client = initialize_s3_client()
        if not s3_client:
            retry_count += 1
            log_message(f"⚠️ Retrying S3 client initialization ({retry_count}/3)...")
            time.sleep(5)
    
    if not s3_client:
        log_message("❌ Screenshot functionality disabled - S3 client initialization failed")
    else:
        log_message("✅ Screenshot functionality enabled")
    
    last_screenshot_time = time.time()
    
    # Initialize timers here
    last_activity_check_time = time.time()
    last_session_status_check_time = time.time()
    
    while True:
        try:
            now = time.time()
            
            # Debug log for tracking status
            if not hasattr(main_loop, 'last_tracking_log'):
                main_loop.last_tracking_log = 0
            if now - main_loop.last_tracking_log >= 60:  # Log tracking status every minute
                log_message(f"🔍 Tracking status: {'Enabled' if tracking_enabled else 'Disabled'}")
                main_loop.last_tracking_log = now

            # Screenshot handling with detailed logging
            if now - last_screenshot_time >= SCREENSHOT_INTERVAL:
                log_message(f"⏰ Screenshot interval reached ({SCREENSHOT_INTERVAL} seconds)")
                if tracking_enabled:
                    log_message("📸 Taking screenshot (tracking enabled)")
                    if take_and_upload_screenshot(s3_client):
                        last_screenshot_time = now
                        log_message(f"⏱️ Next screenshot in {SCREENSHOT_INTERVAL/60} minutes")
                    else:
                        log_message("⚠️ Screenshot failed, will retry in 5 minutes")
                        last_screenshot_time = now - (SCREENSHOT_INTERVAL - 300)
                else:
                    log_message("⏸️ Screenshot skipped (tracking disabled)")
                    last_screenshot_time = now

            # Track activity every second
            if now - last_activity_check_time >= 1:
                active_app = get_active_app_name()
                idle = now - last_input

                if idle < IDLE_THRESHOLD and active_app:
                    aggregate_app_usage(active_app, 1)
                last_activity_check_time = now

            # Log activity summary every minute
            if now - last_log_time >= LOG_INTERVAL:
                log_message("📊 Activity Summary:")
                for app, duration in app_usage.items():
                    minutes = duration // SECONDS_TO_MINUTES
                    seconds = duration % SECONDS_TO_MINUTES
                    hours = minutes // SECONDS_TO_MINUTES
                    remaining_minutes = minutes % SECONDS_TO_MINUTES
                    
                    if hours > 0:
                        log_message(f"   • {app}: {hours}h {remaining_minutes}m {seconds}s")
                    elif minutes > 0:
                        log_message(f"   • {app}: {minutes}m {seconds}s")
                    else:
                        log_message(f"   • {app}: {seconds}s")
                last_log_time = now

            # Check session status every 30 seconds
            if now - last_session_status_check_time >= STATUS_CHECK_INTERVAL:
                check_session_status()
                last_session_status_check_time = now

            # Sync data every 2 minutes if we have data
            if now - last_sync_time >= SYNC_INTERVAL:
                if app_usage:  # Only sync if we have data
                    log_message(f"🔄 Syncing data (Interval: {SYNC_INTERVAL}s)")
                    sync_data()
                last_sync_time = now

            today = date.today().isoformat()
            if last_join_date != today:
                has_joined_today = False
                last_join_date = today

            time.sleep(0.1)  # Reduce CPU usage but maintain accuracy
            
        except Exception as e:
            log_message(f"❌ Error in main loop: {str(e)}")
            time.sleep(5)


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        log_message("👋 Tracker stopped by user")
        # Final sync before exit
        if tracking_enabled and app_usage:
            sync_data()
        sys.exit(0)
