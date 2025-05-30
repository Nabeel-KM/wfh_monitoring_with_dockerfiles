import boto3
import os
from dotenv import load_dotenv
from typing import Optional, Dict, Any

# Load environment variables
load_dotenv()

# AWS settings
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
S3_BUCKET = os.getenv('S3_BUCKET', 'km-wfh-monitoring-bucket')

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

async def upload_file(file_data: bytes, key: str, content_type: str = 'image/png') -> bool:
    """Upload a file to S3."""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=file_data,
            ContentType=content_type
        )
        return True
    except Exception as e:
        print(f"Error uploading file to S3: {e}")
        return False

async def get_file_url(key: str) -> Optional[str]:
    """Get the URL for a file in S3."""
    try:
        url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key}"
        return url
    except Exception as e:
        print(f"Error getting file URL: {e}")
        return None

async def list_files(prefix: str) -> Dict[str, Any]:
    """List files in S3 with a given prefix."""
    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=prefix
        )
        
        files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('.png'):
                    url = await get_file_url(obj['Key'])
                    thumbnail_key = obj['Key'].replace('.png', '-thumb.png')
                    thumbnail_url = await get_file_url(thumbnail_key)
                    
                    files.append({
                        'url': url,
                        'thumbnail_url': thumbnail_url,
                        'key': obj['Key'],
                        'timestamp': obj['LastModified'].isoformat(),
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'].isoformat()
                    })
        
        return {
            'files': sorted(files, key=lambda x: x['key']),
            'count': len(files)
        }
    except Exception as e:
        print(f"Error listing files from S3: {e}")
        return {'files': [], 'count': 0}

async def delete_file(key: str) -> bool:
    """Delete a file from S3."""
    try:
        s3_client.delete_object(
            Bucket=S3_BUCKET,
            Key=key
        )
        return True
    except Exception as e:
        print(f"Error deleting file from S3: {e}")
        return False 