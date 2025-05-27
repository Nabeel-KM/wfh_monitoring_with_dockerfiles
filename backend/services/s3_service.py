"""
S3 service for handling AWS S3 operations.
"""
import os
import boto3
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class S3Service:
    """Service for handling AWS S3 operations"""
    
    def __init__(self):
        """Initialize S3 client"""
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        self.bucket_name = os.getenv('S3_BUCKET', 'km-wfh-monitoring-bucket')
    
    def upload_file(self, file_data, object_key):
        """Upload a file to S3 bucket"""
        try:
            self.s3_client.put_object(
                Body=file_data,
                Bucket=self.bucket_name,
                Key=object_key,
                ContentType='image/png'
            )
            logger.info(f"✅ Successfully uploaded file to S3: {object_key}")
            return True
        except ClientError as e:
            logger.error(f"❌ Error uploading file to S3: {e}")
            return False
    
    def get_file_url(self, object_key, expiration=3600):
        """Generate a presigned URL for an S3 object"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_key
                },
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"❌ Error generating presigned URL: {e}")
            return None
    
    def list_files(self, prefix):
        """List files in S3 bucket with given prefix"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' in response:
                return [item['Key'] for item in response['Contents']]
            return []
        except ClientError as e:
            logger.error(f"❌ Error listing files in S3: {e}")
            return []
    
    def delete_file(self, object_key):
        """Delete a file from S3 bucket"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            logger.info(f"✅ Successfully deleted file from S3: {object_key}")
            return True
        except ClientError as e:
            logger.error(f"❌ Error deleting file from S3: {e}")
            return False

# Create a singleton instance
s3_service = S3Service()