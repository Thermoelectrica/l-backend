"""Authentication repository for token operations"""

from typing import Optional
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.models.auth import InspectorWithPassword, Token
from app.utils.async_wrapper import AsyncWrapper

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/auth.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class AuthRepository:
    """Repository for authentication token operations"""

    async def create_refresh_token(
        self,
        conn,
        token_id: UUID,
        inspector_id: int,
        device_id: str,
        token_hash: str,
        expires_at,
    ) -> Token:
        """Create a new refresh token in the database"""
        row = await queries.create_refresh_token(
            conn,
            id=token_id,
            inspector_id=inspector_id,
            device_id=device_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        return Token(**row)

    async def get_token_by_hash(self, conn, token_hash: str) -> Optional[Token]:
        """Get a refresh token by its hash"""
        row = await queries.get_token_by_hash(conn, token_hash=token_hash)
        if row:
            return Token(**row)
        return None

    async def mark_token_used(self, conn, token_id: UUID) -> None:
        """Mark a token as used (for reuse detection)"""
        await queries.mark_token_used(conn, id=token_id)

    async def revoke_token(self, conn, token_id: UUID) -> None:
        """Revoke a single token"""
        await queries.revoke_token(conn, id=token_id)

    async def revoke_and_replace(self, conn, old_token_id: UUID, new_token_id: UUID) -> None:
        """Revoke old token and link to new one"""
        await queries.revoke_and_replace(conn, old_token_id=old_token_id, new_token_id=new_token_id)

    async def revoke_token_chain(self, conn, token_id: UUID) -> None:
        """Revoke entire token chain (for theft detection)"""
        await queries.revoke_token_chain(conn, token_id=token_id)

    async def get_inspector_by_username(self, conn, username: str) -> Optional[InspectorWithPassword]:
        """Get inspector by username (with password hash for authentication)"""
        row = await queries.get_inspector_by_username(conn, username=username)
        if row:
            return InspectorWithPassword(**row)
        return None

    async def get_inspector_by_id(self, conn, inspector_id: int) -> Optional[InspectorWithPassword]:
        """Get inspector by ID (with password hash for authentication)"""
        row = await queries.get_inspector_by_id(conn, id=inspector_id)
        if row:
            return InspectorWithPassword(**row)
        return None

    async def update_password(self, conn, inspector_id: int, old_password_hash: str, new_password_hash: str) -> bool:
        """
        Update inspector's password hash atomically.
        Returns True if password was updated, False if old password didn't match.
        """
        result = await queries.update_password(
            conn,
            id=inspector_id,
            old_password_hash=old_password_hash,
            new_password_hash=new_password_hash,
        )
        return result is not None

    async def revoke_all_tokens_for_inspector(self, conn, inspector_id: int) -> None:
        """Revoke all tokens for an inspector (e.g., after password change)"""
        await queries.revoke_all_tokens_for_inspector(conn, inspector_id=inspector_id)
