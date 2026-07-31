"""Authentication service with business logic"""

import base64
import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import bcrypt
import jwt

from app.config import settings
from app.models.auth import InspectorWithPassword, TokenPayload, TokenResponse
from app.repositories.auth import AuthRepository

logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication business logic"""

    def __init__(self):
        self.repository = AuthRepository()
        self._private_key: str = self._load_key(settings.private_key, settings.private_key_path, "PRIVATE_KEY")
        self._public_key: str = self._load_key(settings.public_key, settings.public_key_path, "PUBLIC_KEY")

    @staticmethod
    def _load_key(env_value: str | None, file_path: str | None, key_name: str) -> str:
        """Load a single RSA key from env variable or file, raising ValueError if neither is set."""
        if env_value:
            return env_value
        if file_path:
            with open(file_path, "r") as f:
                return f.read()
        raise ValueError(
            f"RSA key '{key_name}' is not configured: set the corresponding environment variable or file path."
        )

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash"""
        return bcrypt.checkpw(password.encode(), password_hash.encode())

    @staticmethod
    def generate_refresh_token() -> str:
        """Generate a random opaque refresh token (256-bit)"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a refresh token using SHA-256"""
        return hashlib.sha256(token.encode()).hexdigest()

    def create_access_token(self, inspector_id: int, device_id: UUID | str, access_level: str) -> str:
        """Create a JWT access token with access level as scope"""
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=settings.access_token_lifetime_min)

        # Ensure device_id is a string
        device_id_str = str(device_id) if isinstance(device_id, UUID) else device_id

        payload = TokenPayload(
            sub=inspector_id,
            dev=device_id_str,
            scope=access_level,
            exp=int(exp.timestamp()),
            iat=int(now.timestamp()),
            iss=settings.jwt_issuer,
            aud=settings.jwt_audience,
        )

        # Convert to dict and ensure proper types for JWT
        payload_dict = payload.model_dump()
        payload_dict["sub"] = str(payload_dict["sub"])  # JWT spec requires sub to be a string
        payload_dict["dev"] = str(payload_dict["dev"])

        return jwt.encode(payload_dict, self._private_key, algorithm="RS256")

    def _yc_verify_access_token(self, token: str) -> Optional[TokenPayload]:
        """
        Проверяет токен через S3 ключи (Basic Auth) для Yandex Cloud
        """
        try:
            expected_access_key = settings.s3_access_key_id
            expected_secret_key = settings.s3_secret_access_key

            if not expected_access_key or not expected_secret_key:
                logger.error("  S3 credentials not found in environment variables")
                return None

            decoded_credentials = base64.b64decode(token).decode("utf-8")

            if ":" not in decoded_credentials:
                logger.warning("  Invalid Basic auth format: missing colon separator")
                return None

            inspector_id, access_key, secret_key = decoded_credentials.split(":")

            current_time = int(time.time())
            if access_key == expected_access_key and secret_key == expected_secret_key:
                return TokenPayload(
                    sub=int(inspector_id),
                    dev="s3-trigger",
                    scope="s3-scope",
                    exp=current_time + 3600,
                    iat=current_time,
                    iss="s3-auth",
                    aud="s3-service",
                )
            else:
                logger.warning("  S3 credentials don't match")
                return None

        except Exception as e:
            logger.error(f"  Error in yc_verify_access_token: {e}")
            return None

    def _jwt_verify_access_token(self, token: str) -> Optional[TokenPayload]:
        """
        Оригинальная функция проверки JWT токена (локальная)
        """
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
            )
            # Convert sub back to int, dev stays as string
            payload["sub"] = int(payload["sub"])
            return TokenPayload(**payload)
        except jwt.InvalidTokenError as e:
            logger.warning(
                "Invalid JWT token",
                extra={"error_type": type(e).__name__, "error": str(e)},
            )
            return None

    def verify_access_token(self, token: str) -> Optional[TokenPayload]:
        """
        Универсальная проверка токена: сначала JWT, потом S3 (Basic Auth)
        """
        jwt_payload = self._jwt_verify_access_token(token)
        if jwt_payload:
            return jwt_payload

        s3_payload = self._yc_verify_access_token(token)
        if s3_payload:
            return s3_payload

        logger.warning("  Авторизация не удалась: ни JWT, ни S3 проверка не прошли")
        return None

    def decode_token_without_validation(self, token: str) -> Optional[TokenPayload]:
        """
        Decode a JWT token without validation (for TRUST_INVALID_TOKENS mode).
        This will accept expired or revoked tokens.
        WARNING: Only use when TRUST_INVALID_TOKENS is enabled for development/testing.
        """
        try:
            # Decode without verification - accepts expired tokens
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                options={"verify_exp": False, "verify_aud": False, "verify_iss": False},
            )
            # Convert sub back to int, dev stays as string
            payload["sub"] = int(payload["sub"])
            return TokenPayload(**payload)
        except jwt.InvalidTokenError as e:
            logger.warning(
                "Failed to decode JWT token even without validation",
                extra={"error_type": type(e).__name__, "error": str(e)},
            )
            return None

    async def login(self, conn, username: str, password: str, device_id: str) -> Optional[TokenResponse]:
        """
        Authenticate user and create tokens.
        Returns None if authentication fails.
        """
        # Get inspector by username
        inspector = await self.repository.get_inspector_by_username(conn, username)
        if not inspector:
            return None

        # Verify password
        if not self.verify_password(password, inspector.password_hash):
            return None

        # Generate tokens with access level as scope
        access_token = self.create_access_token(inspector.id, device_id, inspector.access_level.value)
        refresh_token_string = self.generate_refresh_token()

        # Store refresh token in database
        token_id = uuid4()
        token_hash = self.hash_token(refresh_token_string)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_lifetime_days)

        await self.repository.create_refresh_token(
            conn,
            token_id=token_id,
            inspector_id=inspector.id,
            device_id=device_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        return TokenResponse(access_token=access_token, refresh_token=refresh_token_string)

    async def refresh(self, conn, refresh_token_string: str) -> Optional[TokenResponse]:
        """
        Refresh tokens using a refresh token.
        Returns None if refresh fails.
        Implements token rotation and theft detection.
        """
        token_hash = self.hash_token(refresh_token_string)

        # Get token from database
        token = await self.repository.get_token_by_hash(conn, token_hash)
        if not token:
            return None

        # Check if token is expired
        if token.expires_at < datetime.now(timezone.utc):
            return None

        # Check if token is revoked
        if token.revoked:
            # Token reuse detected - revoke entire chain
            await self.repository.revoke_token_chain(conn, token.id)
            return None

        # Get inspector to retrieve current access level
        inspector = await self.repository.get_inspector_by_id(conn, token.inspector_id)
        if not inspector:
            return None

        # Check if token was recently used (within reuse window)
        if token.used_at:
            reuse_window = timedelta(minutes=settings.reuse_lifetime_min)
            if datetime.now(timezone.utc) - token.used_at < reuse_window:
                # Within reuse window - allow it but don't rotate
                access_token = self.create_access_token(
                    token.inspector_id, token.device_id, inspector.access_level.value
                )
                return TokenResponse(access_token=access_token, refresh_token=refresh_token_string)

        # Mark token as used
        await self.repository.mark_token_used(conn, token.id)

        # Generate new tokens (rotation)
        new_access_token = self.create_access_token(token.inspector_id, token.device_id, inspector.access_level.value)
        new_refresh_token_string = self.generate_refresh_token()

        # Create new refresh token in database
        new_token_id = uuid4()
        new_token_hash = self.hash_token(new_refresh_token_string)
        new_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_lifetime_days)

        await self.repository.create_refresh_token(
            conn,
            token_id=new_token_id,
            inspector_id=token.inspector_id,
            device_id=token.device_id,
            token_hash=new_token_hash,
            expires_at=new_expires_at,
        )

        # Revoke old token and link to new one
        await self.repository.revoke_and_replace(conn, token.id, new_token_id)

        return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token_string)

    async def get_current_inspector(self, conn, token: str) -> Optional[InspectorWithPassword]:
        """Get current inspector from access token (returns internal model with password)"""
        payload = self.verify_access_token(token)
        if not payload:
            return None

        return await self.repository.get_inspector_by_id(conn, payload.sub)

    async def change_password(
        self,
        conn,
        inspector_id: int,
        old_password: str,
        new_password: str,
        device_id: str,
    ) -> Optional[TokenResponse]:
        """
        Change password for an inspector.
        Verifies old password, updates to new password, revokes all tokens, and issues new token pair.

        Args:
            conn: Database connection
            inspector_id: ID of the inspector changing password
            old_password: Current password for verification
            new_password: New password to set
            device_id: Device ID for new token generation

        Returns:
            LoginResponse with new tokens if successful, None if old password is invalid
        """
        # Get inspector by ID
        inspector = await self.repository.get_inspector_by_id(conn, inspector_id)
        if not inspector:
            return None

        # Verify old password
        if not self.verify_password(old_password, inspector.password_hash):
            return None

        # Hash new password
        new_password_hash = self.hash_password(new_password)

        # Update password in database atomically (checks old password hash in DB)
        updated = await self.repository.update_password(conn, inspector_id, inspector.password_hash, new_password_hash)

        # If update failed, old password didn't match (race condition)
        if not updated:
            return None

        # Revoke all existing tokens for this inspector
        await self.repository.revoke_all_tokens_for_inspector(conn, inspector_id)

        # Generate new token pair with access level
        access_token = self.create_access_token(inspector_id, device_id, inspector.access_level.value)
        refresh_token_string = self.generate_refresh_token()

        # Store new refresh token in database
        token_id = uuid4()
        token_hash = self.hash_token(refresh_token_string)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_lifetime_days)

        await self.repository.create_refresh_token(
            conn,
            token_id=token_id,
            inspector_id=inspector_id,
            device_id=device_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        return TokenResponse(access_token=access_token, refresh_token=refresh_token_string)
