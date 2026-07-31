"""S3 service for generating presigned URLs"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, NoCredentialsError

from app.config import settings

logger = logging.getLogger(__name__)


class S3Service:
    """Service for S3 operations"""

    def __init__(self):
        """Initialize S3 client"""
        try:
            # Initialize boto3 client with credentials from settings
            client_config = {
                "region_name": settings.s3_region,
                "aws_access_key_id": settings.s3_access_key_id,
                "aws_secret_access_key": settings.s3_secret_access_key,
            }

            # Configure addressing style for S3-compatible services
            boto_config = Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual" if settings.s3_use_virtual_hosted_style else "path"},
            )
            client_config["config"] = boto_config

            # Add custom endpoint URL if provided (for S3-compatible services)
            if settings.s3_endpoint_host:
                # Construct endpoint URL with proper scheme
                endpoint_url = f"https://{settings.s3_endpoint_host}"
                client_config["endpoint_url"] = endpoint_url

            self.s3_client = boto3.client("s3", **client_config)
            self.bucket_name = settings.s3_bucket_name
            self.expiration = settings.s3_presigned_url_expiration
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise

    def generate_presigned_url(self, image_id: UUID, operation: str = "get_object") -> Optional[Tuple[str, datetime]]:
        """
        Generate a presigned URL for S3 object access.

        Args:
            image_id: UUID of the image (used as S3 object key)
            operation: S3 operation (default: 'get_object' for downloads)

        Returns:
            Tuple of (presigned URL string, expiration datetime) or None if generation fails
        """
        try:
            # Use image_id as the S3 object key
            object_key = f"{image_id}.jpg"

            # Calculate expiration time
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.expiration)

            # Generate presigned URL
            presigned_url = self.s3_client.generate_presigned_url(
                operation,
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=self.expiration,
            )

            return presigned_url, expires_at

        except ClientError as e:
            logger.error(f"Error generating presigned URL for image {image_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating presigned URL for image {image_id}: {str(e)}")
            return None

    def generate_upload_presigned_url(self, image_id: UUID) -> Optional[Tuple[str, datetime]]:
        """
        Generate a presigned URL for uploading an image to S3.

        Args:
            image_id: UUID of the image (used as S3 object key)

        Returns:
            Tuple of (presigned URL string, expiration datetime) for PUT operation or None if generation fails
        """
        return self.generate_presigned_url(image_id, operation="put_object")

    def check_exists(self, image_id: UUID) -> bool:
        """
        Check if an image exists in S3 using HEAD request.

        Args:
            image_id: UUID of the image (used as S3 object key)

        Returns:
            True if the object exists, False otherwise
        """
        try:
            # Use image_id as the S3 object key
            object_key = f"{image_id}.jpg"

            # Issue HEAD request to check existence
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True

        except ClientError as e:
            # If a 404 error is returned, the object does not exist
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                return False
            # For other errors, log and return False
            logger.error(f"Error checking existence for image {image_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking existence for image {image_id}: {str(e)}")
            return False


# Singleton instance
s3_service = S3Service()
