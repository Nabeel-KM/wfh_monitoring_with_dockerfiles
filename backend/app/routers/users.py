from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timezone
from bson import ObjectId
from ..services.mongodb import get_database
from ..utils.helpers import serialize_mongodb_doc

router = APIRouter()

@router.get("/users")
async def get_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100)
):
    """Get a paginated list of users"""
    try:
        db = get_database()
        users_collection = db.users
        
        # Calculate skip value for pagination
        skip = (page - 1) * per_page
        
        # Get total count for pagination
        total_users = await users_collection.count_documents({})
        
        # Get users for current page
        users = await users_collection.find().skip(skip).limit(per_page).to_list(length=per_page)
        
        # Serialize the response
        serialized_users = serialize_mongodb_doc(users)
        
        return {
            "data": serialized_users,
            "pagination": {
                "total": total_users,
                "page": page,
                "per_page": per_page,
                "pages": (total_users + per_page - 1) // per_page
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{username}")
async def get_user(username: str):
    """Get a specific user by username"""
    try:
        db = get_database()
        users_collection = db.users
        
        user = await users_collection.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        return serialize_mongodb_doc(user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users")
async def create_user(username: str, display_name: Optional[str] = None):
    """Create a new user"""
    try:
        db = get_database()
        users_collection = db.users
        
        # Check if user already exists
        existing_user = await users_collection.find_one({"username": username})
        if existing_user:
            raise HTTPException(status_code=400, detail="User already exists")
        
        # Create new user
        user_data = {
            "username": username,
            "display_name": display_name or username,
            "created_at": datetime.now(timezone.utc)
        }
        
        result = await users_collection.insert_one(user_data)
        user_data["_id"] = result.inserted_id
        
        return serialize_mongodb_doc(user_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/users/{username}")
async def update_user(username: str, display_name: Optional[str] = None):
    """Update a user's information"""
    try:
        db = get_database()
        users_collection = db.users
        
        # Check if user exists
        user = await users_collection.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prepare update data
        update_data = {}
        if display_name is not None:
            update_data["display_name"] = display_name
        
        if not update_data:
            return serialize_mongodb_doc(user)
        
        # Update user
        result = await users_collection.update_one(
            {"username": username},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="No changes made")
        
        # Get updated user
        updated_user = await users_collection.find_one({"username": username})
        return serialize_mongodb_doc(updated_user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/users/{username}")
async def delete_user(username: str):
    """Delete a user"""
    try:
        db = get_database()
        users_collection = db.users
        
        # Check if user exists
        user = await users_collection.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Delete user
        result = await users_collection.delete_one({"username": username})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=400, detail="Failed to delete user")
        
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 