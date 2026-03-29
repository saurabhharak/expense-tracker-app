import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


def get_s3_client():
    """Create boto3 S3 client configured for MinIO in dev."""
    kwargs = {
        "aws_access_key_id": settings.S3_ACCESS_KEY,
        "aws_secret_access_key": settings.S3_SECRET_KEY,
        "region_name": settings.S3_REGION,
    }
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    return boto3.client("s3", **kwargs)


def ensure_bucket_exists(client=None) -> None:
    """Create the S3 bucket if it doesn't exist."""
    client = client or get_s3_client()
    try:
        client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
    except ClientError:
        client.create_bucket(Bucket=settings.S3_BUCKET_NAME)


def upload_file(file_bytes: bytes, key: str, content_type: str, client=None) -> str:
    """Upload file to S3. Returns the key."""
    client = client or get_s3_client()
    client.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return key


def generate_presigned_url(key: str, expires_in: int = 3600, client=None) -> str:
    """Generate a presigned download URL."""
    client = client or get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )


def delete_file(key: str, client=None) -> None:
    """Delete a file from S3."""
    client = client or get_s3_client()
    client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
