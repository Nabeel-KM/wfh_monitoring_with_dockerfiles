from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
import boto3
import os
from botocore.exceptions import ClientError
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import hashlib


from ..services.mongodb import get_database
from ..utils.helpers import ensure_timezone_aware

router = APIRouter()

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

def get_s3_client():
    """Get S3 client with error handling."""
    try:
        return boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
    except Exception as e:
        print(f"Error initializing S3 client: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to initialize S3 client")

@router.get("/screenshots")
async def list_screenshots(username: str, date: str):
    """Get screenshots for a user on a specific date."""
    try:
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # Initialize S3 client
        s3_client = get_s3_client()
        S3_BUCKET = os.getenv('S3_BUCKET_NAME', 'km-wfh-monitoring-bucket')
        
        # List objects in the S3 folder
        prefix = f"{username}/{date}/"
        try:
            response = s3_client.list_objects_v2(
                Bucket=S3_BUCKET,
                Prefix=prefix
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error accessing S3: {str(e)}")
        
        # Extract screenshot URLs
        screenshots = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('.png'):
                    url = f"https://{S3_BUCKET}.s3.{os.getenv('AWS_REGION', 'us-east-1')}.amazonaws.com/{obj['Key']}"
                    # Generate thumbnail URL if available
                    thumbnail_key = obj['Key'].replace('.png', '-thumb.png')
                    thumbnail_url = f"https://{S3_BUCKET}.s3.{os.getenv('AWS_REGION', 'us-east-1')}.amazonaws.com/{thumbnail_key}"
                    
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

@router.post("/screenshots/upload")
async def upload_screenshot(
    screenshot: UploadFile = File(...),
    username: str = Form(...),
    date_folder: str = Form(...),
    filename: str = Form(...),
    hash: str = Form(...),
    timestamp: str = Form(...)
):
    """Handle screenshot uploads from the tracker app"""
    try:
        # Read the screenshot data
        screenshot_bytes = await screenshot.read()
        
        # Verify file hash
        file_hash = hashlib.sha256(screenshot_bytes).hexdigest()
        if file_hash != hash:
            raise HTTPException(
                status_code=400, 
                detail="File hash verification failed"
            )

        # Generate S3 key using the provided structure
        s3_key = f"{username}/{date_folder}/{filename}"
        
        # Initialize S3 client
        s3_client = get_s3_client()
        S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'km-wfh-monitoring-bucket')
        
        # Upload to S3 with metadata
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=screenshot_bytes,
                ContentType='image/png',
                Metadata={
                    'username': username,
                    'date': date_folder,
                    'hash': hash,
                    'filename': filename,
                    'timestamp': timestamp,
                    'upload_time': datetime.now(timezone.utc).isoformat()
                }
            )
            
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Screenshot uploaded successfully",
                    "filename": s3_key
                }
            )
            
        except ClientError as e:
            raise HTTPException(
                status_code=500,
                detail=f"S3 upload failed: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Screenshot upload failed: {str(e)}"
        )

# async def upload_screenshot(
#     username: str,
#     file: UploadFile = File(...),
#     timestamp: Optional[datetime] = None
# ):
#     """Upload a screenshot for a user."""
#     try:
#         db = await get_database()
#         if db is None:
#             raise HTTPException(status_code=500, detail="Database connection not available")
            
#         # Get user
#         user = await db.users.find_one({"username": username})
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")
        
#         # Validate file type
#         if not file.content_type.startswith('image/'):
#             raise HTTPException(status_code=400, detail="File must be an image")
        
#         # Ensure timestamp is timezone-aware
#         timestamp = ensure_timezone_aware(timestamp or datetime.now(timezone.utc))
        
#         # Initialize S3 client
#         s3_client = get_s3_client()
#         S3_BUCKET = os.getenv('S3_BUCKET', 'km-wfh-monitoring-bucket')
        
#         # Generate S3 key
#         date_str = timestamp.strftime("%Y-%m-%d")
#         key = f"{username}/{date_str}/{timestamp.isoformat()}.png"
        
#         # Read file content
#         content = await file.read()
        
#         # Upload to S3
#         try:
#             s3_client.put_object(
#                 Bucket=S3_BUCKET,
#                 Key=key,
#                 Body=content,
#                 ContentType="image/png"
#             )
#         except ClientError as e:
#             print(f"S3 upload error: {str(e)}")
#             raise HTTPException(status_code=500, detail="Failed to upload screenshot to S3")
        
#         # Generate URLs
#         url = f"https://{S3_BUCKET}.s3.{os.getenv('AWS_REGION', 'us-east-1')}.amazonaws.com/{key}"
#         thumbnail_key = key.replace('.png', '-thumb.png')
#         thumbnail_url = f"https://{S3_BUCKET}.s3.{os.getenv('AWS_REGION', 'us-east-1')}.amazonaws.com/{thumbnail_key}"
        
#         return {
#             "status": "success",
#             "file_url": url,
#             "thumbnail_url": thumbnail_url,
#             "timestamp": timestamp.isoformat(),
#             "username": username,
#             "date": date_str
#         }
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"Error in upload_screenshot: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))

@router.delete("/screenshots/delete")
async def delete_screenshot(key: str):
    """Delete a screenshot."""
    try:
        # Initialize S3 client
        s3_client = get_s3_client()
        S3_BUCKET = os.getenv('S3_BUCKET', 'km-wfh-monitoring-bucket')
        
        # Delete from S3
        try:
            s3_client.delete_object(
                Bucket=S3_BUCKET,
                Key=key
            )
        except ClientError as e:
            print(f"S3 delete error: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to delete screenshot from S3")
        
        # Also delete thumbnail if it exists
        thumbnail_key = key.replace('.png', '-thumb.png')
        try:
            s3_client.delete_object(
                Bucket=S3_BUCKET,
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