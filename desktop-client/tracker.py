import psutil
import requests
import time
import subprocess
import json
import os
import sys
import platform
import threading

from pynput import mouse, keyboard
from datetime import datetime, timedelta, date, timezone
import hashlib
import logging
import boto3
from PIL import ImageGrab
import io
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import logging.handlers
import queue
import signal

# Platform detection
IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Load environment variables
load_dotenv()

# Directory setup based on platform
if IS_WINDOWS:
    BASE_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'WFH-Tracker')
    LOG_FILE = os.path.join(BASE_DIR, 'logs', 'tracker.log')
    CACHE_FILE = os.path.join(BASE_DIR, 'cache', 'activity_cache.json')
    AGGREGATED_LOG_FILE = os.path.join(BASE_DIR, 'logs', 'aggregated_log.json')
    LAST_SYNC_FILE = os.path.join(BASE_DIR, 'cache', 'last_sync.json')
elif IS_MAC:
    BASE_DIR = os.path.expanduser('~/Library/Application Support/WFH-Tracker')
    LOG_FILE = os.path.join(BASE_DIR, 'logs', 'tracker.log')
    CACHE_FILE = os.path.join(BASE_DIR, 'cache', 'activity_cache.json')
    AGGREGATED_LOG_FILE = os.path.join(BASE_DIR, 'logs', 'aggregated_log.json')
    LAST_SYNC_FILE = os.path.join(BASE_DIR, 'cache', 'last_sync.json')
else:  # Linux
    BASE_DIR = os.path.expanduser('~/.wfh-tracker')
    LOG_FILE = os.path.join(BASE_DIR, 'logs', 'tracker.log')
    CACHE_FILE = os.path.join(BASE_DIR, 'cache', 'activity_cache.json')
    AGGREGATED_LOG_FILE = os.path.join(BASE_DIR, 'logs', 'aggregated_log.json')
    LAST_SYNC_FILE = os.path.join(BASE_DIR, 'cache', 'last_sync.json')

# Constants
API = os.getenv('API_URL', 'https://api-wfh.kryptomind.net/api/activity')
SESSION_STATUS_API = os.getenv('SESSION_STATUS_API', 'https://api-wfh.kryptomind.net/api/session_status')
USER = os.getenv('USER_ID', 'default_user')
IDLE_THRESHOLD = int(os.getenv('IDLE_THRESHOLD', '300'))  # 5 minutes
SYNC_INTERVAL = int(os.getenv('SYNC_INTERVAL', '300'))  # 5 minutes
LOG_INTERVAL = int(os.getenv('LOG_INTERVAL', '60'))  # 1 minute
STATUS_CHECK_INTERVAL = int(os.getenv('STATUS_CHECK_INTERVAL', '30'))  # 30 seconds
SECONDS_TO_MINUTES = 60
SECONDS_TO_HOURS = 3600

# S3 Configuration
SCREENSHOT_INTERVAL = int(os.getenv('SCREENSHOT_INTERVAL', '300'))  # 5 minutes

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
running = True
screenshot_queue = queue.Queue(maxsize=10)  # Queue for screenshot processing with increased capacity
app_usage_lock = threading.Lock()  # Lock for thread-safe app_usage updates
app_tracking_lock = threading.Lock()  # Lock for app tracking to prevent race conditions
last_system_sleep_time = time.time()  # Track system sleep detection


def ensure_directories():
    """Create necessary directories if they don't exist"""
    try:
        log_dir = os.path.join(BASE_DIR, 'logs')
        cache_dir = os.path.join(BASE_DIR, 'cache')
        
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)
        
        # Create and set permissions for log file
        if not os.path.exists(LOG_FILE):
            open(LOG_FILE, 'a').close()
        try:
            os.chmod(LOG_FILE, 0o666)
        except Exception:
            pass  # Windows may not support chmod
        
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
    if IS_LINUX:
        try:
            subprocess.run(['xdotool', '--version'], capture_output=True)
        except FileNotFoundError:
            log_message("❌ Error: xdotool is not installed. Please install it using: sudo apt-get install xdotool")
            sys.exit(1)
    elif IS_MAC:
        try:
            subprocess.run(['osascript', '-e', 'get name of current application'], capture_output=True)
        except FileNotFoundError:
            log_message("❌ Error: osascript is not available. It should be present on macOS by default.")
            sys.exit(1)
    elif IS_WINDOWS:
        try:
            import win32gui  # noqa: F401
            import win32process  # noqa: F401
        except ImportError:
            log_message("❌ Error: pywin32 is not installed. Please install it using: pip install pywin32")
            sys.exit(1)


# Check dependencies on startup
check_dependencies()


def on_activity(*args):
    """Handle any user activity event
    
    Args:
        *args: Variable arguments passed by the event listeners
    """
    global last_input, last_system_sleep_time
    current_time = time.time()
    
    # Check for system sleep/hibernate by detecting large time gaps
    if current_time - last_input > 60:  # If more than a minute passed
        time_gap = current_time - last_input
        # If the gap is unusually large (> 5 minutes), system might have been sleeping
        if time_gap > 300:
            log_message(f"⚠️ Detected possible system sleep/hibernate: {time_gap:.1f} seconds gap")
            last_system_sleep_time = current_time
    
    last_input = current_time


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
        if IS_LINUX:
            # Linux: Use xdotool
            cmd = "xdotool getactivewindow getwindowname"
            window_name = subprocess.check_output(cmd.split()).decode(errors='ignore').strip()
            
            cmd = "xdotool getactivewindow getwindowpid"
            pid = subprocess.check_output(cmd.split()).decode(errors='ignore').strip()
            
            process = psutil.Process(int(pid))
            app_name = process.name()
            
            # Only log when window changes
            if hasattr(get_active_app_name, 'last_app') and get_active_app_name.last_app != app_name:
                log_message(f"🔄 Window changed: {app_name} ({window_name})")
            get_active_app_name.last_app = app_name
            
            return app_name
            
        elif IS_MAC:
            # macOS: Use AppleScript
            script = 'tell application "System Events" to get name of first application process whose frontmost is true'
            proc = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
            app_name = proc.stdout.strip()
            
            if hasattr(get_active_app_name, 'last_app') and get_active_app_name.last_app != app_name:
                log_message(f"🔄 Window changed: {app_name}")
            get_active_app_name.last_app = app_name
            
            return app_name
            
        elif IS_WINDOWS:
            # Windows: Use win32gui
            try:
                import win32gui
                import win32process
                
                hwnd = win32gui.GetForegroundWindow()
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                app_name = process.name()
                window_name = win32gui.GetWindowText(hwnd)
                
                if hasattr(get_active_app_name, 'last_app') and get_active_app_name.last_app != app_name:
                    log_message(f"🔄 Window changed: {app_name} ({window_name})")
                get_active_app_name.last_app = app_name
                
                return app_name
            except Exception as e:
                log_message(f"⚠️ Could not detect active window (Windows): {str(e)}")
                return None
        else:
            log_message("⚠️ Unsupported platform for active window detection")
            return None
    except Exception as e:
        log_message(f"⚠️ Could not detect active window: {str(e)}")
        return None


def aggregate_app_usage(active_app, duration):
    """Aggregate the time spent on each app."""
    global app_usage
    if not active_app:
        return
        
    with app_usage_lock:  # Thread-safe update
        if active_app not in app_usage:
            app_usage[active_app] = 0
        app_usage[active_app] += duration


def save_to_cache(data, synced=False):
    try:
        # Add sync status to cached data
        data['synced'] = synced
        
        # Always replace the cache with the latest data
        # This ensures we don't accumulate values across multiple cache entries
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        
        # Write the single latest entry to the cache file
        with open(CACHE_FILE, 'w') as f:
            json.dump([data], f)  # Store as a list with a single entry
            
        log_message("✅ Latest data cached successfully")
    except Exception as e:
        log_message(f"❌ Error saving to cache: {e}")


# This function is no longer used since we only sync current app_usage data
def send_cached_data():
    """Legacy function - no longer used"""
    log_message("ℹ️ send_cached_data is deprecated - using current activity data only")
        
    # Check if cache file is empty or zero-sized
    if os.path.getsize(CACHE_FILE) == 0:
        log_message("ℹ️ Cache file is empty")
        return
        
    try:
        with open(CACHE_FILE, 'r') as f:
            content = f.read().strip()
            if not content:
                log_message("ℹ️ Cache file is empty")
                return
            cache = json.loads(content)
    except json.JSONDecodeError:
        log_message("⚠️ Cache file corrupted, cannot send cached data")
        # Backup the corrupted file
        backup_file = f"{CACHE_FILE}.bak"
        try:
            os.rename(CACHE_FILE, backup_file)
            log_message(f"📁 Corrupted cache backed up to {backup_file}")
            # Create a new empty cache file
            with open(CACHE_FILE, 'w') as f:
                f.write('[]')
        except Exception as e:
            log_message(f"❌ Error backing up corrupted cache: {e}")
        return
    except Exception as e:
        log_message(f"❌ Error reading cache file: {e}")
        return
        
    if not cache or not isinstance(cache, list):
        log_message("ℹ️ No valid cached data to send")
        return
    
    # Check for outdated entries (from previous days)
    current_date = datetime.now().strftime("%Y-%m-%d")
    outdated_entries = []
    
    for i, entry in enumerate(cache):
        entry_date = entry.get('date')
        if entry_date and entry_date != current_date:
            outdated_entries.append(i)
    
    # Remove outdated entries (in reverse order to avoid index issues)
    for i in sorted(outdated_entries, reverse=True):
        log_message(f"🗑️ Removing outdated cache entry from {cache[i].get('date', 'unknown date')}")
        cache.pop(i)
    
    # If we removed entries, update the cache file
    if outdated_entries:
        log_message(f"🧹 Cleared {len(outdated_entries)} outdated entries from cache")
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    
    if not cache:  # If all entries were outdated
        log_message("ℹ️ No current-day cached data to send after cleaning")
        return
    
    # Only send the most recent cache entry
    if len(cache) > 0:
        # Sort cache entries by timestamp (newest first)
        sorted_cache = sorted(cache, key=lambda x: x.get('timestamp', ''), reverse=True)
        latest_entry = sorted_cache[0]
        
        log_message(f"📤 Sending only the most recent cached data from {latest_entry.get('timestamp')}")
        
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(API, json=latest_entry, headers=headers, timeout=10)
            log_message(f"📡 Response status: {response.status_code}")
            
            if response.status_code == 200:
                log_message("✅ Latest cached data sent successfully")
                # Clear the cache file completely after successful send
                with open(CACHE_FILE, 'w') as f:
                    f.write('[]')
                log_message("🧹 Cache file cleared after successful send")
            else:
                log_message(f"❌ Failed to send latest cached data: {response.text}")
                log_message("⚠️ Keeping cache due to sync errors")
        except Exception as e:
            log_message(f"❌ Error sending latest cached data: {e}")
            log_message("⚠️ Keeping cache due to sync errors")
    else:
        log_message("ℹ️ No cache entries to send")


def load_last_sync():
    if os.path.exists(LAST_SYNC_FILE):
        try:
            with open(LAST_SYNC_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        except (json.JSONDecodeError, Exception) as e:
            log_message(f"⚠️ Error loading last sync data: {e}")
            # Create backup of corrupted file
            backup_file = f"{LAST_SYNC_FILE}.bak"
            try:
                os.rename(LAST_SYNC_FILE, backup_file)
                log_message(f"📁 Corrupted last sync file backed up to {backup_file}")
            except Exception:
                pass
    return {}


def save_last_sync(last_sync):
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(LAST_SYNC_FILE), exist_ok=True)
        
        with open(LAST_SYNC_FILE, 'w') as f:
            json.dump(last_sync, f)
    except Exception as e:
        log_message(f"❌ Error saving last sync data: {e}")


def sync_data():
    """Sync aggregated app usage data with the backend."""
    global app_usage, last_sync_time
    
    # Set a sync timeout to prevent getting stuck
    sync_timeout = 30  # 30 seconds max for sync operation
    sync_start_time = time.time()
    
    try:
        # Make a thread-safe copy of app_usage but don't clear it yet
        # Only clear after successful sync to avoid data loss
        with app_usage_lock:
            if not app_usage:
                log_message("ℹ️ No data to sync")
                return
                
            # Create a copy to work with
            current_app_usage = app_usage.copy()
            log_message("📋 Copied app_usage for sync")
            
        # Use UTC time for consistency with server
        current_time = datetime.now(timezone.utc)
        formatted_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")
        current_date = current_time.strftime("%Y-%m-%d")
        
        # Calculate idle time - ensure consistent units with server
        idle_time = 0
        current_idle = time.time() - last_input
        if current_idle >= IDLE_THRESHOLD:
            # Convert to minutes with consistent precision
            idle_time = round(current_idle / SECONDS_TO_MINUTES, 2)  # Convert to minutes
            log_message(f"⏱️ Current idle time: {idle_time} minutes")
        
        # Convert seconds to minutes before sending
        normalized_app_usage = {}
        total_active_time_seconds = 0
        
        for app, seconds in current_app_usage.items():
            total_active_time_seconds += seconds
            # Convert to minutes with 2 decimal places
            minutes = round(seconds / 60, 2)
            if minutes > 0:  # Only include positive values
                normalized_app_usage[app] = minutes
        
        # Calculate total active time in minutes
        total_active_time = round(total_active_time_seconds / 60, 2)
        
        log_message(f"📊 Total active time: {total_active_time} minutes ({total_active_time_seconds} seconds)")
        
        if not normalized_app_usage:
            log_message("ℹ️ No positive app usage data to sync")
            return
        
        # Log the data being sent for debugging
        log_message("🔍 App usage data being prepared:")
        for app, minutes in normalized_app_usage.items():
            log_message(f"   • {app}: {minutes} minutes")
        
        # Add per-app last_sync info with UTC timestamps
        app_sync_info = {}
        for app in normalized_app_usage:
            # Ensure we use UTC timestamp for all apps
            app_sync_info[app] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # Add display name if available
        display_name = os.getenv('DISPLAY_NAME', '')
        
        # Include both apps and app_usage fields for backward compatibility
        data = {
            'username': USER,
            'display_name': display_name if display_name else USER,
            'apps': normalized_app_usage,
            'app_usage': normalized_app_usage,  # Add app_usage field for backward compatibility
            'timestamp': formatted_time,
            'date': current_date,
            'app_sync_info': app_sync_info,
            'idle_time': idle_time,
            'total_active_time': total_active_time,
            'system_info': {
                'platform': platform.system(),
                'version': platform.version(),
                'hostname': platform.node()
            }
        }
        
        # Validate data before sending
        if not validate_data_before_sync(data):
            log_message("⚠️ Data validation failed, not sending to server")
            # Save to cache for later analysis
            save_to_cache(data)
            return
        
        # Only send data if user is currently in the channel
        if tracking_enabled:
            log_message(f"📤 Attempting to sync data to {API}")
            # Implement retry mechanism with exponential backoff
            max_retries = 3
            retry_delay = 2  # Start with 2 seconds delay
            response = None
            
            for retry in range(max_retries):
                try:
                    headers = {'Content-Type': 'application/json'}
                    if retry > 0:
                        log_message(f"🔄 Retry attempt {retry}/{max_retries} after {retry_delay}s delay")
                    
                    log_message(f"📦 Sending payload: {json.dumps(data)}")
                    try:
                        response = requests.post(API, json=data, headers=headers, timeout=15)
                        log_message(f"📡 Response status: {response.status_code}")
                        log_message(f"📡 Response body: {response.text}")
                        
                        # Break the retry loop if successful
                        if response.status_code == 200:
                            break
                            
                        # If we get here, the request failed but didn't throw an exception
                        if retry < max_retries - 1:  # Don't sleep after the last retry
                            log_message(f"⚠️ Request failed with status {response.status_code}, retrying...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                    except requests.exceptions.ConnectionError:
                        log_message("⚠️ Network connection error, will retry later")
                        if retry >= max_retries - 1:
                            save_to_cache(data)
                            return
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        
                except requests.exceptions.RequestException as e:
                    log_message(f"❌ Request error: {str(e)}")
                    if retry < max_retries - 1:  # Don't sleep after the last retry
                        log_message(f"⚠️ Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        # Save data to cache on final retry failure
                        log_message("❌ All retry attempts failed, saving to cache")
                        save_to_cache(data)
                        return
            
            # Make sure app_sync_info is properly set for each app with UTC timestamps
            data['app_sync_info'] = {app: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") for app in normalized_app_usage}
            
            # Check if we have a valid response and it was successful
            if response and response.status_code == 200:
                log_message("✅ Data synced successfully")
                # Now that sync was successful, clear the app_usage data
                with app_usage_lock:
                    # Subtract the synced data from app_usage
                    for app, seconds in current_app_usage.items():
                        if app in app_usage:
                            app_usage[app] = max(0, app_usage[app] - seconds)
                            if app_usage[app] == 0:
                                del app_usage[app]
                    log_message("🧹 Cleared synced data from app_usage")
            else:
                log_message(f"❌ Failed to sync data: {response.status_code if response else 'No response'}")
                # Save the current data to cache
                save_to_cache(data)
        else:
            log_message("🔒 Not sending data to backend (user not in wfh-monitoring channel)")
            # Always cache data if user has joined today, even if not currently in channel
            if has_joined_today:
                log_message("💾 Caching data for later sync when user rejoins channel")
                save_to_cache(data)
            else:
                log_message("🗒️ Not caching data: user has not joined the channel today")
    except Exception as e:
        log_message(f"❌ Unexpected error during sync: {str(e)}")
        # Reset last_sync_time to retry sooner
        last_sync_time = time.time() - (SYNC_INTERVAL / 2)
    finally:
        # Check if sync took too long
        sync_duration = time.time() - sync_start_time
        if sync_duration > 5:  # Log warning if sync takes more than 5 seconds
            log_message(f"⚠️ Sync operation took {sync_duration:.2f} seconds")
        # Ensure sync doesn't exceed timeout
        if sync_duration > sync_timeout:
            log_message("⚠️ Sync operation timed out, forcing completion")
            # Reset last_sync_time to retry sooner
            last_sync_time = time.time() - (SYNC_INTERVAL / 2)



def log_aggregated_data():
    """Log aggregated app usage data to the log file."""
    global app_usage
    if app_usage:
        log_message("📊 Activity Summary:")
        for app, duration in app_usage.items():
            minutes = duration // SECONDS_TO_MINUTES
            seconds = duration % SECONDS_TO_MINUTES
            if minutes > 0:
                log_message(f"   • {app}: {minutes}m {seconds}s")
            else:
                log_message(f"   • {app}: {seconds}s")
    else:
        log_message("💤 No activity recorded in this interval")


def check_session_status():
    """Check the user's session status using the backend API."""
    global tracking_enabled, has_joined_today, last_join_date, last_status_check_time, app_usage
    try:
        log_message(f"🔍 Checking session status for user: {USER}")
        # Reduce timeout to prevent hanging
        response = requests.get(f"{SESSION_STATUS_API}?username={USER}", timeout=3)
        log_message(f"📡 Session status response: {response.status_code}")
        
        if response.status_code == 200:
            session_status = response.json()
            log_message(f"📊 Session data: {json.dumps(session_status)}")
            
            # Check for channel joined status
            is_in_channel = session_status.get('channel') == 'wfh-monitoring'
            today = date.today().isoformat()
            
            if is_in_channel:
                # User is in the channel
                if not has_joined_today or last_join_date != today:
                    # First time joining today
                    has_joined_today = True
                    last_join_date = today
                    log_message("✅ User joined today for the first time.")
                    # Reset app usage when joining for the first time today
                    with app_usage_lock:
                        app_usage.clear()
                        log_message("🔄 Resetting app usage for new day")
                
                if not tracking_enabled:
                    # User just joined the channel
                    log_message(f"✅ User joined the channel. Starting tracking.")
                    tracking_enabled = True
                    
                    # Only sync current app_usage data as it's the most accurate
                    if app_usage:
                        log_message("📤 Syncing current activity data")
                        sync_data()
                    else:
                        log_message("ℹ️ No current activity data to sync")
                        
                    # Clear any cached data without sending it
                    if os.path.exists(CACHE_FILE) and os.path.getsize(CACHE_FILE) > 0:
                        log_message("🧹 Clearing cached data without sending")
                        with open(CACHE_FILE, 'w') as f:
                            f.write('[]')
            elif tracking_enabled:
                # User left the channel
                log_message(f"⏹️ User left the channel. Stopping tracking.")
                # Cache current data before disabling tracking
                sync_data()
                tracking_enabled = False
                
        else:
            log_message(f"❌ Failed to fetch session status: {response.status_code}")
            log_message(f"Response: {response.text}")
            # Don't change tracking state on API failure
            
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Error checking session status: {e}")
        # Don't change tracking state on network error
        time.sleep(5)
        
    # Safety check: if it's a new day but we haven't reset state yet
    today = date.today().isoformat()
    if last_join_date and last_join_date != today:
        log_message("📅 Detected day change during session check")
        has_joined_today = False
        # Don't reset app_usage here as that's handled in the main loop


def initialize_s3_client():
    """Initialize S3 client - No longer needed as we use FastAPI backend"""
    return None


def take_screenshot():
    """Capture a screenshot and return it as bytes"""
    try:
        # Capture screenshot
        screenshot = ImageGrab.grab()
        
        # Convert to bytes with compression
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='JPEG', quality=70)  # 70% quality for good compression
        img_byte_arr.seek(0)
        
        return img_byte_arr.getvalue()
    except Exception as e:
        log_message(f"❌ Error capturing screenshot: {e}")
        return None


def upload_screenshot_to_backend(screenshot_bytes):
    """Upload screenshot to backend API"""
    if not screenshot_bytes:
        return False

    try:
        # Calculate file hash for integrity verification
        file_hash = hashlib.sha256(screenshot_bytes).hexdigest()
        
        # Generate timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        
        # Prepare the multipart form data
        files = {
            'screenshot': ('screenshot.jpg', screenshot_bytes, 'image/jpeg')
        }
        
        data = {
            'username': USER,
            'timestamp': timestamp,
            'hash': file_hash
        }
        
        # Send to backend API
        response = requests.post(
            f"{API}/screenshots/upload",
            files=files,
            data=data,
            timeout=30
        )
        
        if response.status_code == 200:
            log_message(f"✅ Screenshot uploaded successfully: {timestamp}")
            return True
        else:
            log_message(f"❌ Failed to upload screenshot: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Error uploading screenshot: {e}")
        return False
    except Exception as e:
        log_message(f"❌ Unexpected error uploading screenshot: {e}")
        return False


def screenshot_worker():
    """Worker thread for processing screenshots"""
    while running:
        try:
            # Check if it's time to take a screenshot
            current_time = time.time()
            if current_time - last_screenshot_time >= SCREENSHOT_INTERVAL:
                # Take and upload screenshot
                screenshot_bytes = take_screenshot()
                if screenshot_bytes:
                    upload_screenshot_to_backend(screenshot_bytes)
                    global last_screenshot_time
                    last_screenshot_time = current_time
                
            # Sleep for a short interval to prevent high CPU usage
            time.sleep(10)
            
        except Exception as e:
            log_message(f"❌ Error in screenshot worker: {e}")
            time.sleep(30)  # Wait longer on error


def take_and_upload_screenshot():
    """Take and upload a screenshot immediately"""
    try:
        screenshot_bytes = take_screenshot()
        if screenshot_bytes:
            return upload_screenshot_to_backend(screenshot_bytes)
        return False
    except Exception as e:
        log_message(f"❌ Error in take_and_upload_screenshot: {e}")
        return False


def handle_exit_signal(signum, frame):
    """Handle exit signals gracefully"""
    global running
    log_message(f"🛑 Received signal {signum}, shutting down...")
    running = False
    
    # Force exit after a short delay if cleanup doesn't complete
    def force_exit():
        time.sleep(5)  # Give cleanup 5 seconds to complete
        log_message("⚠️ Forcing exit after timeout")
        os._exit(1)  # Force exit
        
    # Start a daemon thread to force exit if needed
    force_exit_thread = threading.Thread(target=force_exit, daemon=True)
    force_exit_thread.start()

def validate_data_before_sync(data):
    """Validate data before sending to backend"""
    # Check required fields
    required_fields = ['username', 'apps', 'timestamp', 'date']
    for field in required_fields:
        if field not in data:
            log_message(f"⚠️ Missing required field: {field}")
            return False
    
    # Validate username
    if not data['username'] or not isinstance(data['username'], str):
        log_message("⚠️ Invalid username")
        return False
    
    # Validate apps data
    if not isinstance(data['apps'], dict):
        log_message("⚠️ Apps data must be a dictionary")
        return False
    
    # Validate timestamp format
    try:
        datetime.strptime(data['timestamp'], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        log_message("⚠️ Invalid timestamp format")
        return False
    
    # Validate date format
    try:
        datetime.strptime(data['date'], "%Y-%m-%d")
    except ValueError:
        log_message("⚠️ Invalid date format")
        return False
    
    return True

def main_loop():
    """Main tracking loop"""
    global last_input, last_sync_time, last_log_time, last_status_check_time, app_usage
    global last_screenshot_time, has_joined_today, last_join_date, running, tracking_enabled, last_system_sleep_time
    
    # Don't set up signal handlers in a thread - they only work in the main thread
    
    log_message("✅ Starting tracker...")
    setup_input_listeners()
    
    # Track the current day to detect day changes
    current_day = datetime.now().strftime("%Y-%m-%d")
    log_message(f"📅 Current day: {current_day}")
    
    # Initialize tracking state
    has_joined_today = False
    tracking_enabled = False
    last_join_date = None
    
    # Clear app usage on startup to ensure clean state
    with app_usage_lock:
        app_usage.clear()
        
    log_message("🔄 Initializing tracking state - waiting for user to join channel")
    
    # Start screenshot worker thread
    screenshot_thread = threading.Thread(target=screenshot_worker, daemon=True)
    screenshot_thread.start()
    log_message("✅ Screenshot worker thread started")
    
    last_screenshot_time = time.time()
    
    # Initialize timers here
    last_activity_check_time = time.time()
    last_session_status_check_time = time.time()
    last_memory_check_time = time.time()
    
    # Memory usage tracking
    process = psutil.Process(os.getpid())
    
    while running:
        try:
            now = time.time()
            
            # Debug log for tracking status
            if not hasattr(main_loop, 'last_tracking_log'):
                main_loop.last_tracking_log = 0
            if now - main_loop.last_tracking_log >= 60:  # Log tracking status every minute
                log_message(f"🔍 Tracking status: {'Enabled' if tracking_enabled else 'Disabled'}")
                main_loop.last_tracking_log = now

            # Monitor memory usage every 5 minutes
            if now - last_memory_check_time >= 300:  # 5 minutes
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB
                log_message(f"🧠 Memory usage: {memory_mb:.2f} MB")
                last_memory_check_time = now

            # Screenshot handling with detailed logging
            if now - last_screenshot_time >= SCREENSHOT_INTERVAL:
                log_message(f"⏰ Screenshot interval reached ({SCREENSHOT_INTERVAL} seconds)")
                if tracking_enabled:
                    log_message("📸 Taking screenshot (tracking enabled)")
                    if take_and_upload_screenshot():
                        last_screenshot_time = now
                        log_message(f"⏱️ Next screenshot in {SCREENSHOT_INTERVAL/60} minutes")
                    else:
                        log_message("⚠️ Screenshot failed, will retry in 5 minutes")
                        last_screenshot_time = now - (SCREENSHOT_INTERVAL - 300)
                else:
                    log_message("⏸️ Screenshot skipped (tracking disabled or no S3 client)")
                    last_screenshot_time = now

            # Track activity every second
            if now - last_activity_check_time >= 1:
                active_app = get_active_app_name()
                idle = now - last_input

                # Use lock to prevent race conditions in app tracking
                with app_tracking_lock:
                    if idle < IDLE_THRESHOLD and active_app:
                        aggregate_app_usage(active_app, 1)
                    elif idle >= IDLE_THRESHOLD:
                        # Log when user becomes idle (only once when crossing the threshold)
                        if not hasattr(main_loop, 'last_idle_state') or not main_loop.last_idle_state:
                            idle_minutes = round(idle / 60, 1)
                            log_message(f"💤 User is idle for {idle_minutes} minutes")
                            main_loop.last_idle_state = True
                    else:
                        # Reset idle state when user becomes active again
                        if hasattr(main_loop, 'last_idle_state') and main_loop.last_idle_state:
                            log_message("🔄 User is active again")
                            main_loop.last_idle_state = False
                
                last_activity_check_time = now

            # Log activity summary every minute
            if now - last_log_time >= LOG_INTERVAL:
                with app_usage_lock:  # Thread-safe access
                    if app_usage:
                        log_message("📊 Activity Summary:")
                        for app, duration in app_usage.items():
                            minutes = duration // SECONDS_TO_MINUTES
                            seconds = duration % SECONDS_TO_MINUTES
                            hours = minutes // 60
                            remaining_minutes = minutes % 60
                            
                            if hours > 0:
                                log_message(f"   • {app}: {hours}h {remaining_minutes}m {seconds}s")
                            elif minutes > 0:
                                log_message(f"   • {app}: {minutes}m {seconds}s")
                            else:
                                log_message(f"   • {app}: {seconds}s")
                    else:
                        log_message("💤 No activity recorded in this interval")
                last_log_time = now

            # Check session status every 30 seconds
            if now - last_session_status_check_time >= STATUS_CHECK_INTERVAL:
                check_session_status()
                last_session_status_check_time = now

            # Sync data every 2 minutes if we have data
            if now - last_sync_time >= SYNC_INTERVAL:
                with app_usage_lock:  # Thread-safe access
                    if app_usage:  # Only sync if we have data
                        log_message(f"🔄 Syncing data (Interval: {SYNC_INTERVAL}s)")
                        # Use a separate thread for syncing to prevent blocking the main loop
                        sync_thread = threading.Thread(target=sync_data, daemon=True)
                        sync_thread.start()
                        # Wait for a maximum of 10 seconds for the sync to complete
                        sync_thread.join(timeout=10)
                        if sync_thread.is_alive():
                            log_message("⚠️ Sync thread is taking too long, continuing without waiting")
                last_sync_time = now

            # Check if the day has changed
            today = date.today().isoformat()
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            if today_str != current_day:
                log_message(f"📅 Day changed from {current_day} to {today_str}")
                
                # If user was tracking, sync data before day change
                if tracking_enabled and app_usage:
                    log_message("📤 Syncing data before day change")
                    sync_data()
                
                log_message("🧹 Clearing cached data from previous day")
                
                if os.path.exists(CACHE_FILE):
                    # Backup the old cache
                    backup_file = f"{CACHE_FILE}.{current_day}"
                    try:
                        os.rename(CACHE_FILE, backup_file)
                        log_message(f"📁 Previous day's cache backed up to {backup_file}")
                        # Create a new empty cache file
                        with open(CACHE_FILE, 'w') as f:
                            f.write('[]')
                    except Exception as e:
                        log_message(f"❌ Error backing up previous day's cache: {e}")
                
                # Reset tracking state for the new day
                has_joined_today = False
                last_join_date = today
                current_day = today_str
                
                # Reset app usage for the new day
                with app_usage_lock:
                    if app_usage:
                        log_message("🔄 Resetting app usage for new day")
                        app_usage.clear()
            
            # Regular check for join date
            elif last_join_date != today:
                has_joined_today = False
                last_join_date = today

            time.sleep(0.1)  # Reduce CPU usage but maintain accuracy
            
        except Exception as e:
            log_message(f"❌ Error in main loop: {str(e)}")
            time.sleep(5)


def cleanup():
    """Perform cleanup operations before exit"""
    global running, app_usage
    running = False
    log_message("🧹 Performing cleanup...")
    
    # Set a timeout for the entire cleanup process
    cleanup_start = time.time()
    max_cleanup_time = 10  # Maximum 10 seconds for cleanup
    
    try:
        # Final sync before exit - with direct sync instead of threading
        if tracking_enabled and app_usage:
            with app_usage_lock:
                log_message("📤 Performing final data sync")
                try:
                    # Directly call sync_data instead of using a thread
                    current_time = datetime.now()
                    formatted_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")
                    current_date = current_time.strftime("%Y-%m-%d")
                    
                    # Convert seconds to minutes
                    normalized_app_usage = {
                        app: round(seconds / SECONDS_TO_MINUTES, 2)
                        for app, seconds in app_usage.items()
                    }
                    
                    # Calculate total active time
                    total_active_time = sum(normalized_app_usage.values())
                    
                    # Create minimal data for direct sync with UTC timestamp
                    data = {
                        'username': USER,
                        'display_name': os.getenv('DISPLAY_NAME', USER),
                        'apps': normalized_app_usage,
                        'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                        'date': datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        'app_sync_info': {app: formatted_time for app in normalized_app_usage},
                        'total_active_time': total_active_time  # Add total active time
                    }
                    
                    # Direct API call with increased timeout
                    headers = {'Content-Type': 'application/json'}
                    response = requests.post(API, json=data, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        log_message("✅ Final data sync completed successfully")
                        app_usage.clear()
                    else:
                        log_message(f"❌ Final sync failed: {response.status_code}")
                        save_to_cache(data)
                        log_message("✅ Final data saved to cache")
                except Exception as e:
                    log_message(f"❌ Error during final sync: {e}")
                    # Save to cache as a fallback
                    if app_usage:
                        current_time = datetime.now()
                        formatted_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")
                        current_date = current_time.strftime("%Y-%m-%d")
                        
                        # Convert seconds to minutes
                        normalized_app_usage = {
                            app: round(seconds / SECONDS_TO_MINUTES, 2)
                            for app, seconds in app_usage.items()
                        }
                        
                        # Calculate total active time
                        total_active_time = sum(normalized_app_usage.values())
                        
                        # Create minimal data for cache
                        data = {
                            'username': USER,
                            'display_name': os.getenv('DISPLAY_NAME', USER),
                            'apps': normalized_app_usage,
                            'timestamp': formatted_time,
                            'date': current_date,
                            'app_sync_info': {app: formatted_time for app in normalized_app_usage},
                            'total_active_time': total_active_time  # Add total active time
                        }
                        save_to_cache(data)
                        log_message("✅ Final data saved to cache")
        
        # Clear screenshot queue instead of waiting for it to empty
        while not screenshot_queue.empty():
            try:
                screenshot_queue.get_nowait()
                screenshot_queue.task_done()
            except queue.Empty:
                break
        
        # Check if we're taking too long
        if time.time() - cleanup_start > max_cleanup_time - 2:
            log_message("⚠️ Cleanup taking too long, exiting now")
            return
            
    except Exception as e:
        log_message(f"⚠️ Error during cleanup: {e}")
    finally:
        log_message("👋 Tracker stopped")

if __name__ == "__main__":
    try:
        # Set process name for better identification
        try:
            import setproctitle
            setproctitle.setproctitle("wfh-tracker")
        except ImportError:
            pass
        
        # Set up signal handlers in the main thread
        signal.signal(signal.SIGINT, handle_exit_signal)
        signal.signal(signal.SIGTERM, handle_exit_signal)
            
        # Set a watchdog timer to force exit if program hangs
        def watchdog():
            time.sleep(60)  # Wait 60 seconds
            log_message("⚠️ Watchdog timer expired, forcing exit")
            os._exit(2)
        
        # Run main loop directly in the main thread
        main_loop()
            
    except KeyboardInterrupt:
        log_message("👋 Tracker stopped by user")
    except Exception as e:
        log_message(f"❌ Fatal error: {str(e)}")
    finally:
        # Set a timeout for cleanup
        cleanup_thread = threading.Thread(target=cleanup)
        cleanup_thread.start()
        cleanup_thread.join(timeout=5)  # Wait max 5 seconds for cleanup
        
        if cleanup_thread.is_alive():
            log_message("⚠️ Cleanup timed out, forcing exit")
        
        # Force exit to ensure we don't hang
        log_message("🚪 Exiting tracker")
        os._exit(0)
