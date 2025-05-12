# Save this as test_screenshot.py
import boto3
from PIL import ImageGrab
import io

s3_client = boto3.client(
    's3',
    aws_access_key_id='AKIAXNGUVRA3FXBGECNN',
    aws_secret_access_key='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',
    region_name='us-east-1'
)

# Take screenshot
screenshot = ImageGrab.grab()
img_byte_arr = io.BytesIO()
screenshot.save(img_byte_arr, format='PNG')
img_byte_arr.seek(0)

# Upload to S3
s3_client.upload_fileobj(
    img_byte_arr,
    'km-wfh-monitoring-bucket',
    'test-screenshot.png',
    ExtraArgs={'ContentType': 'image/png'}
)