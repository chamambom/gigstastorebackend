import boto3
from .settings import settings


# Initialize S3 client for Cloudflare R2
def get_r2_client():
    """Get configured R2 client"""
    return boto3.client(
        's3',
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name='auto'  # Cloudflare R2 uses 'auto'
    )


# Global R2 client instance
r2_client = get_r2_client()
