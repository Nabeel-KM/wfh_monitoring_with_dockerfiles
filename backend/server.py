from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from apscheduler.schedulers.background import BackgroundScheduler
from mongodb import users_collection, sessions_collection, activities_collection, daily_summaries_collection

app = Flask(__name__)
CORS(app)

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
            user_id = users_collection.insert_one({
                "username": data['username'],
                "email": data.get('email'),
                "is_active": True,
                "created_at": datetime.utcnow()
            }).inserted_id
        else:
            print(f"✅ User found: {user}")
            user_id = user["_id"]

        # Update or create session
        session = sessions_collection.find_one({"user_id": user_id})
        if event == "joined":
            # Handle joining the channel
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
    data = request.json
    print(f"Received activity data: {data}")  # Log the incoming data

    try:
        # Get the user
        user = users_collection.find_one({"username": data['username']})
        if not user:
            print(f"❌ User not found: {data['username']}")
            return jsonify({'error': 'User not found'}), 404

        # Update or insert activity
        activities_collection.update_one(
            {"user_id": user["_id"]},  # Match the user by user_id
            {
                "$set": {
                    "active_apps": data.get('active_apps', []),
                    "active_app": data.get('active_app', 'unknown'),
                    "idle_time": data.get('idle_time', '0 mins'),
                    "timestamp": datetime.fromisoformat(data['timestamp'])
                }
            },
            upsert=True  # Create a new record if it doesn't exist
        )

        return jsonify({'ok': True})
    except Exception as e:
        print(f"❌ Error processing activity: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    try:
        users = users_collection.find()
        dashboard_data = []

        for user in users:
            user_id = user["_id"]
            username = user["username"]

            # Fetch the latest session for the user
            latest_session = sessions_collection.find_one(
                {"user_id": user_id},
                sort=[("timestamp", -1)]
            )

            # Fetch the latest activity for the user
            latest_activity = activities_collection.find_one(
                {"user_id": user_id},
                sort=[("timestamp", -1)]
            )

            # Fetch the daily summary for the user
            today = datetime.utcnow().date()
            daily_summary = daily_summaries_collection.find_one(
                {"user_id": user_id, "date": str(today)}
            )
            total_idle_time = daily_summary["total_idle_time"] if daily_summary else 0

            # Prepare the response data
            dashboard_data.append({
                "username": username,
                "channel": latest_session["channel"] if latest_session else "N/A",
                "screen_shared": latest_session["screen_shared"] if latest_session else False,
                "screen_share_time": latest_session["screen_share_time"] if latest_session else 0,
                "timestamp": latest_session["timestamp"] if latest_session else None,
                "active_app": latest_activity["active_app"] if latest_activity else "Unknown",
                "active_apps": latest_activity["active_apps"] if latest_activity else [],
                "total_idle_time": total_idle_time // 60,  # Convert seconds to minutes
                "total_working_hours": latest_session.get("total_working_hours", 0) // 3600,  # Convert seconds to hours
                "daily_summaries": user.get("daily_summaries", [])
            })

        return jsonify(dashboard_data)
    except Exception as e:
        print(f"❌ Error fetching dashboard data: {e}")
        return jsonify({"error": "Failed to fetch dashboard data"}), 500

@app.route('/api/session_status', methods=['GET'])
def session_status():
    try:
        username = request.args.get('username')
        if not username:
            return jsonify({'error': 'Username is required'}), 400

        # Find the user
        user = users_collection.find_one({"username": username})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Check the user's session
        session = sessions_collection.find_one({"user_id": user["_id"], "screen_shared": True})
        if session:
            return jsonify({'screen_shared': True, 'channel': session.get('channel', 'N/A')})
        else:
            return jsonify({'screen_shared': False})

    except Exception as e:
        print(f"❌ Error fetching session status: {e}")
        return jsonify({'error': 'Failed to fetch session status'}), 500

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
