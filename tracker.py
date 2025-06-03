import os
import time
import json
import requests
import pyautogui
import schedule
from datetime import datetime, timezone
from PIL import Image
import io
import logging
from pathlib import Path
import hashlib
import threading
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class ScreenshotManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_url = config.get('api_url', 'http://localhost:8000')
        self.username = config.get('username')
        self.screenshot_interval = config.get('screenshot_interval', 300)  # 5 minutes default
        self.screenshot_quality = config.get('screenshot_quality', 70)  # JPEG quality
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self._last_screenshot_time = 0
        self._upload_lock = threading.Lock()

    def capture_screenshot(self) -> Optional[bytes]:
        """Capture a screenshot and return it as bytes"""
        try:
            # Capture screenshot
            screenshot = pyautogui.screenshot()
            
            # Convert to bytes with compression
            img_byte_arr = io.BytesIO()
            screenshot.save(img_byte_arr, format='JPEG', quality=self.screenshot_quality)
            img_byte_arr.seek(0)
            
            return img_byte_arr.getvalue()
        except Exception as e:
            logger.error(f"❌ Error capturing screenshot: {e}")
            return None

    def upload_screenshot(self, image_data: bytes) -> bool:
        """Upload screenshot to the server"""
        if not image_data:
            return False

        # Calculate file hash for integrity verification
        file_hash = hashlib.sha256(image_data).hexdigest()
        
        # Prepare the multipart form data
        files = {
            'file': ('screenshot.jpg', image_data, 'image/jpeg')
        }
        data = {
            'username': self.username
        }

        # Add authentication headers
        headers = {
            'Authorization': f"Bearer {self.config.get('auth_token')}"
        }

        # Try to upload with retries
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.api_url}/screenshot/upload",
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    logger.info("✅ Screenshot uploaded successfully")
                    return True
                else:
                    logger.warning(f"⚠️ Upload attempt {attempt + 1} failed: {response.status_code} - {response.text}")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Network error during upload attempt {attempt + 1}: {e}")
            
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
        
        return False

    def should_take_screenshot(self) -> bool:
        """Check if it's time to take a screenshot based on interval"""
        current_time = time.time()
        if current_time - self._last_screenshot_time >= self.screenshot_interval:
            self._last_screenshot_time = current_time
            return True
        return False

    def process_screenshot(self):
        """Process and upload a screenshot if needed"""
        if not self.should_take_screenshot():
            return

        with self._upload_lock:
            try:
                # Capture screenshot
                image_data = self.capture_screenshot()
                if image_data:
                    # Upload screenshot
                    self.upload_screenshot(image_data)
            except Exception as e:
                logger.error(f"❌ Error in screenshot process: {e}")

def main():
    # Load configuration
    config_path = Path.home() / '.wfh_tracker' / 'config.json'
    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"❌ Error loading config: {e}")
        return

    # Initialize screenshot manager
    screenshot_manager = ScreenshotManager(config)

    # Schedule screenshot capture
    schedule.every(screenshot_manager.screenshot_interval).seconds.do(
        screenshot_manager.process_screenshot
    )

    logger.info("🚀 Starting WFH Tracker...")
    logger.info(f"📸 Screenshot interval: {screenshot_manager.screenshot_interval} seconds")

    # Main loop
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("👋 Shutting down WFH Tracker...")
            break
        except Exception as e:
            logger.error(f"❌ Error in main loop: {e}")
            time.sleep(5)  # Wait before retrying

if __name__ == "__main__":
    main() 