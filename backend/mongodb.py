from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://db:27017")
client = MongoClient(MONGO_URI)
db = client["wfh_monitoring"]

# Collections
users_collection = db["users"]
sessions_collection = db["sessions"]
activities_collection = db["activities"]
daily_summaries_collection = db["daily_summaries"]
app_usage_collection = db["app_usage"]  # Add this line