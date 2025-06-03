from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
import boto3
import os
from botocore.exceptions import ClientError
import hashlib

from ..services.mongodb import get_database
from ..utils.helpers import ensure_timezone_aware

router = APIRouter(
    prefix="",
    tags=["screenshots"],
    responses={404: {"description": "Not found"}},
)

class ScreenshotData(BaseModel):
    url: str
    thumbnail_url: Optional[str] = None
    key: str
    timestamp: str
    size: int
    last_modified: str

    model_config = ConfigDict(from_attributes=True)

class ScreenshotsResponse(BaseModel):
    screenshots: List[ScreenshotData] = []
    count: int = 0
    username: str
    date: str
    timestamp: str
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)

S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')

@router.get("/")
async def list_screenshots(username: str, date: str):
    """Get screenshots for a user on a specific date."""
    try:
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # List objects in the S3 folder
        prefix = f"{username}/{date}/"
        try:
            response = s3_client.list_objects_v2(
                Bucket=S3_BUCKET_NAME,
                Prefix=prefix
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error accessing S3: {str(e)}")
        
        # Extract screenshot URLs
        screenshots = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('.jpg'):  # Changed from .png to .jpg to match upload format
                    url = f"https://{S3_BUCKET_NAME}.s3.{os.getenv('AWS_REGION', 'us-east-1')}.amazonaws.com/{obj['Key']}"
                    # Generate thumbnail URL if available
                    thumbnail_key = obj['Key'].replace('.jpg', '-thumb.jpg')  # Changed from .png to .jpg
                    thumbnail_url = f"https://{S3_BUCKET_NAME}.s3.{os.getenv('AWS_REGION', 'us-east-1')}.amazonaws.com/{thumbnail_key}"
                    
                    screenshots.append(ScreenshotData(
                        url=url,
                        thumbnail_url=thumbnail_url,
                        key=obj['Key'],
                        timestamp=obj['LastModified'].isoformat(),
                        size=obj['Size'],
                        last_modified=obj['LastModified'].isoformat()
                    ))
        
        # Sort screenshots by timestamp
        screenshots.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Prepare response
        response = ScreenshotsResponse(
            screenshots=screenshots,
            count=len(screenshots),
            username=username,
            date=date,
            timestamp=datetime.now(timezone.utc).isoformat(),
            message="No screenshots found for this date" if not screenshots else None
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload")
async def upload_screenshot(
    screenshot: UploadFile = File(...),
    username: str = Form(...),
    timestamp: str = Form(...),
    hash: str = Form(...)
):
    """Handle screenshot uploads from the tracker app"""
    try:
        # Read the screenshot data
        screenshot_bytes = await screenshot.read()
        
        # Verify file hash
        file_hash = hashlib.sha256(screenshot_bytes).hexdigest()
        if file_hash != hash:
            raise HTTPException(status_code=400, detail="File hash verification failed")
        
        # Generate S3 filename
        filename = f"{username}/{datetime.now(timezone.utc).strftime('%Y-%m-%d')}/{timestamp}_{hash[:8]}.jpg"
        
        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=filename,
            Body=screenshot_bytes,
            ContentType='image/jpeg',
            Metadata={
                'user': username,
                'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'hash': hash,
                'timestamp': timestamp
            }
        )
        
        return JSONResponse(
            status_code=200,
            content={"message": "Screenshot uploaded successfully", "filename": filename}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete")
async def delete_screenshot(key: str):
    """Delete a screenshot."""
    try:
        # Delete from S3
        try:
            s3_client.delete_object(
                Bucket=S3_BUCKET_NAME,
                Key=key
            )
        except ClientError as e:
            print(f"S3 delete error: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to delete screenshot from S3")
        
        # Also delete thumbnail if it exists
        thumbnail_key = key.replace('.jpg', '-thumb.jpg')
        try:
            s3_client.delete_object(
                Bucket=S3_BUCKET_NAME,
                Key=thumbnail_key
            )
        except ClientError:
            pass  # Ignore if thumbnail doesn't exist
        
        return {
            "status": "success",
            "deleted_key": key,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in delete_screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 