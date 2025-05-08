import psutil
import requests
import time
import subprocess
import json
import os
from pynput import mouse, keyboard
from datetime import datetime
import hashlib

API = 'http://localhost:5000/api/activity'
SCREEN_SHARING_API = 'http://localhost:5000/api/session_status'
USER = 'nabeelkm_55353'
CACHE_FILE = 'activity_cache.json'
LOG_FILE = 'tracker.log'
IDLE_THRESHOLD = 300  # 5 minutes

last_input = time.time()

def log_message(message):
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n")

def hash_username(username):
    return hashlib.sha256(username.encode()).hexdigest()

def on_input(event):
    global last_input
    last_input = time.time()

mouse.Listener(on_click=on_input).start()
keyboard.Listener(on_press=on_input).start()

def get_active_app_name():
    try:
        win_id = subprocess.check_output(['xdotool', 'getactivewindow']).decode().strip()
        pid = subprocess.check_output(['xdotool', 'getwindowpid', win_id]).decode().strip()
        process = psutil.Process(int(pid))
        return process.name().lower()
    except Exception as e:
        log_message(f"❌ Could not detect active app: {e}")
        return "unknown"

def get_active_apps():
    target_apps = ['code', 'chrome', 'slack', 'firefox', 'nautilus', 'terminal', 'gnome-terminal', 'warp', 'discord', 'spotify', 'vlc']
    apps = set()
    for p in psutil.process_iter(['name']):
        name = p.info['name']
        if name and any(name.lower().startswith(app) for app in target_apps):
            apps.add(name.lower())
    return list(apps)

def save_to_cache(data):
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f:
            json.dump([], f)
    with open(CACHE_FILE, 'r+') as f:
        cache = json.load(f)
        cache.append(data)
        f.seek(0)
        json.dump(cache, f)

def send_cached_data():
    if not os.path.exists(CACHE_FILE):
        return
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)
    for data in cache:
        try:
            requests.post(API, json=data)
            log_message(f"✅ Sent cached data: {data}")
        except Exception as e:
            log_message(f"❌ Error sending cached data: {e}")
            return
    os.remove(CACHE_FILE)

send_cached_data()

while True:
    now = time.time()
    idle = now - last_input

    try:
        response = requests.get(f'{SCREEN_SHARING_API}?username={USER}')
        screen_sharing_active = response.json().get('screen_shared', False)
    except Exception as e:
        log_message(f"❌ Error checking screen sharing status: {e}")
        screen_sharing_active = False

    if screen_sharing_active and idle < IDLE_THRESHOLD:
        data = {
            'username': USER,  # Use the plain username
            'active_apps': get_active_apps(),
            'active_app': get_active_app_name(),
            'idle_time': f'{int(idle // 60)} mins',
            'timestamp': datetime.now().isoformat()
        }

        try:
            requests.post(API, json=data)
            log_message(f"✅ Sent: {data['active_app']} | Idle: {data['idle_time']} | Apps: {data['active_apps']}")
        except Exception as e:
            log_message(f"❌ Error sending: {e}")
            save_to_cache(data)

    time.sleep(100)
