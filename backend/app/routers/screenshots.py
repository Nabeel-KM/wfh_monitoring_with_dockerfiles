from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict

from ..services.mongodb import get_collections
from ..services.s3 import upload_file, get_file_url, list_files, delete_file
from ..utils.helpers import ensure_timezone_aware

router = APIRouter()

class ScreenshotData(BaseModel):
    username: str
    timestamp: Optional[datetime] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

@router.post("/screenshots/upload")
async def upload_screenshot(
    username: str,
    file: UploadFile = File(...),
    timestamp: Optional[datetime] = None
):
    """Upload a screenshot for a user."""
    try:
        collections = get_collections()
        users = collections["users"]
        
        # Get user
        user = await users.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Ensure timestamp is timezone-aware
        timestamp = ensure_timezone_aware(timestamp or datetime.now(timezone.utc))
        
        # Generate S3 key
        date_str = timestamp.strftime("%Y/%m/%d")
        key = f"screenshots/{username}/{date_str}/{timestamp.isoformat()}.png"
        
        # Read file content
        content = await file.read()
        
        # Upload to S3
        success = await upload_file(content, key, "image/png")
        if not success:
            raise HTTPException(status_code=500, detail="Failed to upload screenshot")
        
        # Get file URL
        file_url = await get_file_url(key)
        
        return {
            "status": "success",
            "file_url": file_url,
            "timestamp": timestamp.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/screenshots/list")
async def list_screenshots(
    username: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """List screenshots for a user."""
    try:
        collections = get_collections()
        users = collections["users"]
        
        # Get user
        user = await users.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Build prefix
        prefix = f"screenshots/{username}/"
        if start_date:
            prefix += start_date.strftime("%Y/%m/%d")
        
        # List files
        files = await list_files(prefix)
        
        # Filter by date range if needed
        if start_date or end_date:
            filtered_files = []
            for file in files["files"]:
                file_date = datetime.fromisoformat(file["key"].split("/")[-1].replace(".png", ""))
                if start_date and file_date < start_date:
                    continue
                if end_date and file_date > end_date:
                    continue
                filtered_files.append(file)
            files["files"] = filtered_files
            files["count"] = len(filtered_files)
        
        return files
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/screenshots/delete")
async def delete_screenshot(key: str):
    """Delete a screenshot."""
    try:
        # Delete from S3
        success = await delete_file(key)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete screenshot")
        
        return {"status": "success"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/screenshots/url")
async def get_screenshot_url(key: str):
    """Get URL for a screenshot."""
    try:
        # Get file URL
        file_url = await get_file_url(key)
        if not file_url:
            raise HTTPException(status_code=404, detail="Screenshot not found")
        
        return {
            "file_url": file_url
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 