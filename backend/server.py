from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta, timezone
from bson.objectid import ObjectId
from pymongo import UpdateOne  # Add this import
from apscheduler.schedulers.background import BackgroundScheduler
from mongodb import users_collection, sessions_collection, activities_collection, daily_summaries_collection, app_usage_collection
from bson import json_util
import json
import boto3
import os

app = Flask(__name__)
CORS(app)

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)

S3_BUCKET = os.getenv('S3_BUCKET', 'km-wfh-monitoring-bucket')

def serialize_mongodb_doc(doc):
    """Helper function to serialize MongoDB documents"""
    if isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.isoformat()
    elif isinstance(doc, dict):
        return {k: serialize_mongodb_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_mongodb_doc(item) for item in doc]
    return doc

@app.route('/api/session', methods=['POST'])
def session():
    data = request.json
    print(f"✅ Received session data: {data}")

    try:
        # Validate required fields
        required_fields = ['username', 'channel', 'screen_shared', 'event']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            print(f"❌ Missing fields: {missing_fields}")
            return jsonify({'error': f'Missing fields: {missing_fields}'}), 400

        # Validate event type
        event = data.get('event')
        if event not in ['joined', 'left', 'started_streaming', 'stopped_streaming']:
            print(f"❌ Invalid event type: {event}")
            return jsonify({'error': 'Invalid event type'}), 400

        # Get or create user
        user = users_collection.find_one({"username": data['username']})
        if not user:
            print(f"🔍 User not found. Creating new user: {data['username']}")
            result = users_collection.insert_one({
                "username": data['username'],
                "created_at": datetime.utcnow()
            })
            user_id = result.inserted_id
            print(f"✅ Created new user with ID: {user_id}")
        else:
            user_id = user["_id"]

        # Get current session
        session = sessions_collection.find_one({"user_id": user_id}, sort=[("timestamp", -1)])

        # Handle different events
        if event == "joined":
            if session:
                print(f"🔄 Updating session for user_id: {user_id} on join")
                sessions_collection.update_one(
                    {"_id": session["_id"]},
                    {"$set": {"channel": data['channel'], "event": event, "start_time": datetime.utcnow()}}
                )
            else:
                print(f"➕ Creating new session for user_id: {user_id} on join")
                sessions_collection.insert_one({
                    "user_id": user_id,
                    "channel": data['channel'],
                    "screen_shared": False,
                    "screen_share_time": 0,
                    "start_time": datetime.utcnow(),
                    "stop_time": None,
                    "event": event,
                    "timestamp": datetime.utcnow()
                })
        elif event == "left":
            # Handle leaving the channel
            if session:
                print(f"🔄 User left the channel for user_id: {user_id}")
                start_time = session.get("start_time")
                stop_time = datetime.utcnow()

                # Calculate working hours for this session
                if start_time:
                    duration = (stop_time - start_time).total_seconds()
                    print(f"⏱ Calculated working duration: {duration} seconds for user_id: {user_id}")

                    # Update session with stop_time and increment total working hours
                    sessions_collection.update_one(
                        {"_id": session["_id"]},
                        {
                            "$set": {"stop_time": stop_time, "channel": None, "event": event},
                            "$inc": {"total_working_hours": int(duration)}
                        }
                    )
                else:
                    print(f"❌ No start_time found for user_id: {user_id}")
            else:
                print(f"❌ No session found for user_id: {user_id}")
                return jsonify({'error': 'No session found'}), 404

        elif event == "started_streaming":
            # Start screen sharing
            if session:
                print(f"🔄 Resuming session for user_id: {user_id}")
                sessions_collection.update_one(
                    {"_id": session["_id"]},
                    {"$set": {"screen_shared": True, "start_time": datetime.utcnow(), "channel": data['channel'], "event": event}}
                )
            else:
                print(f"➕ Creating new session for user_id: {user_id}")
                sessions_collection.insert_one({
                    "user_id": user_id,
                    "channel": data['channel'],
                    "screen_shared": True,
                    "screen_share_time": 0,
                    "start_time": datetime.utcnow(),
                    "event": event,
                    "timestamp": datetime.utcnow()
                })
        elif event == "stopped_streaming":
            # Stop screen sharing and calculate duration
            if session and session.get("start_time"):
                start_time = session["start_time"]
                end_time = datetime.utcnow()
                duration = (end_time - start_time).total_seconds()
                print(f"⏱ Calculated screen share duration: {duration} seconds for user_id: {user_id}")

                sessions_collection.update_one(
                    {"_id": session["_id"]},
                    {"$inc": {"screen_share_time": int(duration)},
                     "$set": {"screen_shared": False, "start_time": None, "event": event, "timestamp": end_time}}
                )
            else:
                print(f"❌ No active screen sharing session found for user_id: {user_id}")
                return jsonify({'error': 'No active screen sharing session found'}), 400

        return jsonify({'ok': True})
    except Exception as e:
        print(f"❌ Error processing session: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/activity', methods=['POST'])
def activity():
    try:
        data = request.json
        print(f"📥 Received activity data: {data}")

        # Get the user
        user = users_collection.find_one({"username": data['username']})
        if not user:
            print(f"❌ User not found: {data['username']}")
            return jsonify({'error': 'User not found'}), 404

        current_date = data.get('date') or datetime.now().strftime("%Y-%m-%d")
        app_usage = data.get('app_usage', {})
        app_sync_info = data.get('app_sync_info', {})
        sync_timestamp = data.get('timestamp')

        # Update activities collection with deduplication
        for app_name, duration in app_usage.items():
            sync_ts = app_sync_info.get(app_name, data.get('timestamp'))
            activity_doc = activities_collection.find_one({
                "user_id": user["_id"],
                "app_name": app_name,
                "date": current_date
            })
            last_sync = activity_doc.get("last_sync", "") if activity_doc else ""
            if not last_sync or sync_ts > last_sync:
                activities_collection.update_one(
                    {
                        "user_id": user["_id"],
                        "app_name": app_name,
                        "date": current_date
                    },
                    {
                        "$inc": {"total_time": duration},
                        "$set": {
                            "last_updated": datetime.now(),
                            "username": user['username'],
                            "last_sync": sync_ts
                        }
                    },
                    upsert=True
                )
            else:
                print(f"⚠️ Duplicate or old sync for {app_name} on {current_date}, ignoring.")

        # Update daily summary
        total_time = sum(app_usage.values())
        daily_summaries_collection.update_one(
            {
                "user_id": user["_id"],
                "date": current_date
            },
            {
                "$inc": {"total_active_time": total_time},
                "$set": {
                    "last_updated": datetime.now(),
                    "username": user['username']
                },
                "$push": {
                    "app_summaries": {
                        "timestamp": data.get('timestamp'),
                        "apps": app_usage
                    }
                }
            },
            upsert=True
        )

        print(f"✅ Successfully updated activity data")
        return jsonify({'success': True})

    except Exception as e:
        print(f"❌ Error processing activity: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    try:
        users = list(users_collection.find())
        # Use UTC for all date calculations
        current_date = datetime.now(timezone.utc).date()
        dashboard_data = []
        for user in users:
            # Get latest session
            latest_session = sessions_collection.find_one(
                {"user_id": user["_id"]},
                sort=[("timestamp", -1)]
            )

            # --- Filter sessions for the current day using UTC ---
            day_start = datetime.combine(current_date, datetime.min.time(), tzinfo=timezone.utc)
            day_end = datetime.combine(current_date, datetime.max.time(), tzinfo=timezone.utc)
            sessions_today = list(sessions_collection.find({
                "user_id": user["_id"],
                "start_time": {"$gte": day_start, "$lte": day_end},
                "stop_time": {"$gte": day_start, "$lte": day_end}
            }))
            session_durations = [(s["stop_time"] - s["start_time"]).total_seconds() for s in sessions_today if s["stop_time"] > s["start_time"]]
            total_session_seconds = sum(session_durations)
            total_session_hours = round(max(total_session_seconds, 0) / 3600, 2)

            # --- Duty start/end time logic ---
            duty_start_session = sessions_collection.find_one({
                "user_id": user["_id"],
                "event": "joined",
                "start_time": {"$gte": day_start, "$lte": day_end}
            }, sort=[("start_time", 1)])
            duty_end_session = sessions_collection.find_one({
                "user_id": user["_id"],
                "event": "left",
                "stop_time": {"$gte": day_start, "$lte": day_end}
            }, sort=[("stop_time", -1)])
            duty_start_time = duty_start_session["start_time"].astimezone(timezone.utc).isoformat() if duty_start_session and duty_start_session.get("start_time") else None
            duty_end_time = duty_end_session["stop_time"].astimezone(timezone.utc).isoformat() if duty_end_session and duty_end_session.get("stop_time") else None

            # --- Aggregate app usage from activities collection for today (accurate, UTC) ---
            day_str = current_date.strftime("%Y-%m-%d")
            activities_today = list(activities_collection.find({
                "user_id": user["_id"],
                "date": day_str
            }))
            app_usage = [
                {"app_name": a["app_name"], "total_time": max(a.get("total_time", 0), 0)}
                for a in activities_today
            ]
            total_active_time = round(sum(a["total_time"] for a in app_usage), 2)
            active_apps = [a["app_name"] for a in app_usage if a.get("total_time", 0) > 0]
            most_active_app = max(app_usage, key=lambda x: x.get("total_time", 0), default=None)

            # Get daily summary for today (for idle time, etc.)
            daily_summary = daily_summaries_collection.find_one({
                "user_id": user["_id"],
                "date": day_str
            })
            total_idle_time = daily_summary.get("total_idle_time", 0) if daily_summary else 0

            user_data = {
                "username": user["username"],
                "channel": latest_session.get("channel") if latest_session else None,
                "screen_shared": latest_session.get("screen_shared", False) if latest_session else False,
                "timestamp": latest_session.get("timestamp").astimezone(timezone.utc).isoformat() if latest_session and latest_session.get("timestamp") else None,
                "active_app": most_active_app["app_name"] if most_active_app else None,
                "active_apps": active_apps,
                "screen_share_time": latest_session.get("screen_share_time", 0) if latest_session else 0,
                "total_idle_time": total_idle_time,
                "total_active_time": total_active_time,  # minutes
                "total_session_time": total_session_hours,  # hours
                "duty_start_time": duty_start_time,
                "duty_end_time": duty_end_time,
                "app_usage": app_usage,
                "most_used_app": most_active_app["app_name"] if most_active_app else None,
                "most_used_app_time": round(most_active_app["total_time"], 2) if most_active_app else 0,
                "daily_summaries": list(daily_summaries_collection.find(
                    {"user_id": user["_id"]},
                    sort=[("date", -1)],
                    limit=7
                ))
            }
            dashboard_data.append(user_data)
        serialized_data = serialize_mongodb_doc(dashboard_data)
        response = jsonify(serialized_data)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"❌ Error in dashboard endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/session_status', methods=['GET'])
def session_status():
    try:
        username = request.args.get('username')
        if not username:
            return jsonify({'error': 'Username required'}), 400

        user = users_collection.find_one({"username": username})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Get latest session
        session = sessions_collection.find_one(
            {"user_id": user["_id"]},
            sort=[("timestamp", -1)]
        )

        return jsonify({
            "screen_shared": session.get("screen_shared", False) if session else False,
            "channel": session.get("channel", None) if session else None,
            "timestamp": session.get("timestamp", None) if session else None,
            "active_app": session.get("active_app", None) if session else None,
            "active_apps": session.get("active_apps", []) if session else []
        })

    except Exception as e:
        print(f"Error in session status: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/verify_data', methods=['GET'])
def verify_data():
    """Endpoint to verify data in collections"""
    try:
        username = request.args.get('username')
        if not username:
            return jsonify({'error': 'Username required'}), 400

        user = users_collection.find_one({"username": username})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Get today's date
        today = datetime.now().strftime("%Y-%m-%d")

        # Get activities
        activities = list(activities_collection.find({
            "user_id": user["_id"],
            "date": today
        }))

        # Get daily summary
        daily_summary = daily_summaries_collection.find_one({
            "user_id": user["_id"],
            "date": today
        })

        return jsonify({
            'activities': [
                {
                    'app_name': a['app_name'],
                    'total_time': a['total_time'],
                    'last_updated': a['last_updated'].isoformat()
                } for a in activities
            ],
            'daily_summary': {
                'total_active_time': daily_summary['total_active_time'] if daily_summary else 0,
                'last_updated': daily_summary['last_updated'].isoformat() if daily_summary else None
            } if daily_summary else None
        })

    except Exception as e:
        print(f"❌ Error verifying data: {e}")
        return jsonify({'error': str(e)}), 500

def reset_screen_share_time():
    try:
        print("⏰ Running daily reset task...")

        # Get yesterday's date
        yesterday = (datetime.utcnow() - timedelta(days=1)).date()

        # Aggregate screen share time and idle time for each user
        sessions = sessions_collection.find({"screen_share_time": {"$gt": 0}})
        for session in sessions:
            user_id = session["user_id"]
            screen_share_time = session["screen_share_time"]

            # Fetch the latest activity for idle time
            latest_activity = activities_collection.find_one(
                {"user_id": user_id},
                sort=[("timestamp", -1)]
            )
            total_idle_time = latest_activity.get("idle_time", "0 mins") if latest_activity else "0 mins"

            # Convert idle time to seconds
            idle_time_seconds = int(total_idle_time.split()[0]) * 60 if "mins" in total_idle_time else 0

            # Store in daily summaries
            daily_summaries_collection.update_one(
                {"user_id": user_id, "date": str(yesterday)},
                {
                    "$inc": {
                        "total_screen_share_time": screen_share_time,
                        "total_idle_time": idle_time_seconds
                    }
                },
                upsert=True
            )

            # Reset screen share time
            sessions_collection.update_one(
                {"_id": session["_id"]},
                {"$set": {"screen_share_time": 0}}
            )

        print("✅ Daily reset task completed successfully.")
    except Exception as e:
        print(f"❌ Error during daily reset task: {e}")

def update_screen_share_time():
    try:
        print("⏰ Running incremental screen share time update...")

        # Fetch all active screen sharing sessions
        active_sessions = sessions_collection.find({"screen_shared": True, "start_time": {"$ne": None}})
        for session in active_sessions:
            user_id = session["user_id"]
            start_time = session["start_time"]
            current_time = datetime.utcnow()

            # Calculate the elapsed time since the last update
            elapsed_time = (current_time - start_time).total_seconds()
            print(f"⏱ Incrementing screen share time by {elapsed_time} seconds for user_id: {user_id}")

            # Increment the screen_share_time and update the start_time
            sessions_collection.update_one(
                {"_id": session["_id"]},
                {
                    "$inc": {"screen_share_time": int(elapsed_time)},
                    "$set": {"start_time": current_time}
                }
            )

        print("✅ Incremental screen share time update completed.")
    except Exception as e:
        print(f"❌ Error during incremental screen share time update: {e}")

# Schedule the incremental update task
scheduler = BackgroundScheduler()
scheduler.add_job(update_screen_share_time, 'interval', minutes=1)  # Run every minute
scheduler.add_job(reset_screen_share_time, 'cron', hour=0, minute=0)  # Run at midnight UTC
scheduler.start()

@app.route('/api/history', methods=['GET'])
def history():
    try:
        username = request.args.get('username')
        days = int(request.args.get('days', 30))
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days-1)
        users = []
        if username:
            user = users_collection.find_one({"username": username})
            if not user:
                return jsonify({'error': 'User not found'}), 404
            users = [user]
        else:
            users = list(users_collection.find())
        history_data = []
        for user in users:
            user_id = user["_id"]
            user_history = {"username": user["username"], "days": []}
            for i in range(days):
                day = start_date + timedelta(days=i)
                day_str = day.strftime("%Y-%m-%d")
                # Sessions for the day
                sessions = list(sessions_collection.find({
                    "user_id": user_id,
                    "start_time": {"$exists": True, "$ne": None, "$gte": datetime.combine(day, datetime.min.time())},
                    "stop_time": {"$exists": True, "$ne": None, "$lte": datetime.combine(day, datetime.max.time())}
                }))
                total_session_seconds = sum((s["stop_time"] - s["start_time"]).total_seconds() for s in sessions)
                total_session_hours = round(total_session_seconds / 3600, 2)
                first_activity = min((s["start_time"] for s in sessions), default=None)
                last_activity = max((s["stop_time"] for s in sessions), default=None)
                # Activities for the day
                activities = list(activities_collection.find({
                    "user_id": user_id,
                    "date": day_str
                }))
                app_usage = [
                    {"app_name": a["app_name"], "total_time": a.get("total_time", 0)}
                    for a in activities
                ]
                most_active_app = max(app_usage, key=lambda x: x.get("total_time", 0), default=None)
                # Daily summary for the day
                daily_summary = daily_summaries_collection.find_one({
                    "user_id": user_id,
                    "date": day_str
                })
                total_active_time = daily_summary.get("total_active_time", 0) if daily_summary else 0
                total_idle_time = daily_summary.get("total_idle_time", 0) if daily_summary else 0
                user_history["days"].append({
                    "date": day_str,
                    "total_active_time": round(total_active_time / 60, 2),
                    "total_session_time": total_session_hours,
                    "total_idle_time": total_idle_time,
                    "first_activity": first_activity.isoformat() if first_activity else None,
                    "last_activity": last_activity.isoformat() if last_activity else None,
                    "app_usage": app_usage,
                    "most_used_app": most_active_app["app_name"] if most_active_app else None,
                    "most_used_app_time": round(most_active_app["total_time"], 2) if most_active_app else 0
                })
            history_data.append(user_history)
        serialized_data = serialize_mongodb_doc(history_data)
        return jsonify(serialized_data)
    except Exception as e:
        print(f"❌ Error in history endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/screenshots', methods=['GET'])
def list_screenshots():
    try:
        username = request.args.get('username')
        date = request.args.get('date')
        
        if not username or not date:
            return jsonify({'error': 'Username and date are required'}), 400
            
        # List objects in the S3 folder
        prefix = f"{username}/{date}/"
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=prefix
        )
        
        # Extract screenshot URLs
        screenshots = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('.png'):
                    url = f"https://{S3_BUCKET}.s3.{os.getenv('AWS_REGION', 'us-east-1')}.amazonaws.com/{obj['Key']}"
                    screenshots.append({
                        'url': url,
                        'key': obj['Key'],
                        'last_modified': obj['LastModified'].isoformat()
                    })
        
        return jsonify({
            'screenshots': sorted(screenshots, key=lambda x: x['key'])
        })
        
    except Exception as e:
        print(f"❌ Error listing screenshots: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
