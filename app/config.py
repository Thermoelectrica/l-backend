"""Application configuration"""

from typing import Optional
from urllib.parse import urlparse, urlunparse

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    database_password: Optional[str] = None  # Optional override for database password
    db_driver: str = "asyncpg"  # Options: "asyncpg" or "psycopg2"

    # Authentication settings
    require_auth: bool = True  # Set to False to disable authentication
    trust_invalid_tokens: bool = False  # Set to True to accept expired or revoked tokens (for development/testing)
    access_token_lifetime_min: int = 15
    refresh_token_lifetime_days: int = 7
    reuse_lifetime_min: int = 1
    jwt_issuer: str = "l-inspector-backend"
    jwt_audience: str = "l-inspector-app"

    # RSA keys - can be provided directly as env vars or via file paths
    private_key: Optional[str] = None  # Direct key content from env var
    public_key: Optional[str] = None  # Direct key content from env var
    private_key_path: str = "private.pem"  # Fallback to file path
    public_key_path: str = "public.pem"  # Fallback to file path

    # Logging settings
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_json: bool = True  # Enable structured JSON logging

    # Optimistic locking settings
    disable_optimistic_locking: bool = False  # Set to True to disable optimistic locking (for testing only)

    # S3 settings
    s3_region: str = "ru-central1"
    # S3 endpoint host (e.g., "storage.yandexcloud.net" for Yandex, "s3.amazonaws.com" for AWS)
    s3_endpoint_host: Optional[str] = "storage.yandexcloud.net"
    # Use virtual-hosted-style URLs (bucket.host) instead of path-style (host/bucket)
    s3_use_virtual_hosted_style: bool = True
    s3_bucket_name: str
    s3_access_key_id: Optional[str] = None
    s3_secret_access_key: Optional[str] = None
    s3_presigned_url_expiration: int = 3600  # URL expiration in seconds (default: 1 hour)

    class Config:
        env_file = ".env"

    def get_database_url(self) -> str:
        """Get database URL with password override if provided"""
        if self.database_password is None:
            return self.database_url

        # Parse the URL and replace the password
        parsed = urlparse(self.database_url)

        # Reconstruct netloc with new password
        if parsed.username:
            netloc = f"{parsed.username}:{self.database_password}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
        else:
            netloc = parsed.netloc

        # Reconstruct the full URL
        return urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )


settings = Settings()  # type: ignore
