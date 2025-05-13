from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from pymongo import UpdateOne  # Add this import
from apscheduler.schedulers.background import BackgroundScheduler
from mongodb import users_collection, sessions_collection, activities_collection, daily_summaries_collection, app_usage_collection
from bson import json_util
import json

app = Flask(__name__)
CORS(app)

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

        # Update activities collection
        bulk_operations = []
        for app_name, duration in app_usage.items():
            bulk_operations.append(UpdateOne(
                {
                    "user_id": user["_id"],
                    "app_name": app_name,
                    "date": current_date
                },
                {
                    "$inc": {
                        "total_time": duration  # Use the duration from app_usage directly
                    },
                    "$set": {
                        "last_updated": datetime.now(),
                        "username": user['username']
                    }
                },
                upsert=True
            ))

        if bulk_operations:
            result = activities_collection.bulk_write(bulk_operations)
            print(f"✅ Updated {len(bulk_operations)} activities")

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
        # Get all users
        users = list(users_collection.find())
        
        # Get current date
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Process each user
        dashboard_data = []
        for user in users:
            # Get latest session
            latest_session = sessions_collection.find_one(
                {"user_id": user["_id"]},
                sort=[("timestamp", -1)]
            )
            
            # Get daily summary for today
            daily_summary = daily_summaries_collection.find_one({
                "user_id": user["_id"],
                "date": current_date
            })
            
            # Aggregate app usage from today's app_summaries
            app_usage = []
            if daily_summary and "app_summaries" in daily_summary:
                app_totals = {}
                for summary in daily_summary["app_summaries"]:
                    for app, time in summary["apps"].items():
                        app_totals[app] = app_totals.get(app, 0) + time
                app_usage = [{"app_name": app, "total_time": total_time} for app, total_time in app_totals.items()]
            
            # Get active apps (apps with nonzero usage)
            active_apps = [app["app_name"] for app in app_usage if app.get("total_time", 0) > 0]
            
            # Get most active app
            most_active_app = None
            if app_usage:
                most_active_app = max(app_usage, key=lambda x: x.get("total_time", 0))
            
            user_data = {
                "username": user["username"],
                "channel": latest_session.get("channel") if latest_session else None,
                "screen_shared": latest_session.get("screen_shared", False) if latest_session else False,
                "timestamp": latest_session.get("timestamp").isoformat() if latest_session and latest_session.get("timestamp") else None,
                "active_app": most_active_app["app_name"] if most_active_app else None,
                "active_apps": active_apps,
                "screen_share_time": latest_session.get("screen_share_time", 0) if latest_session else 0,
                "total_idle_time": daily_summary.get("total_idle_time", 0) if daily_summary else 0,
                "total_working_hours": daily_summary.get("total_working_hours", 0) if daily_summary else 0,
                "app_usage": app_usage,
                "daily_summaries": list(daily_summaries_collection.find(
                    {"user_id": user["_id"]},
                    sort=[("date", -1)],
                    limit=7
                ))
            }
            
            dashboard_data.append(user_data)
        
        # Add cache control headers
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
