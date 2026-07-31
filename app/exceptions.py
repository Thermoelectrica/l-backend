"""Custom exception handlers"""

import logging

import asyncpg
import psycopg2
import psycopg2.errors
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.models import BaseError

logger = logging.getLogger(__name__)


class ConcurrentModificationError(Exception):
    """Raised when concurrent modification is detected"""

    def __init__(self, conflict_error):
        self.conflict_error = conflict_error
        super().__init__(conflict_error.message)


class BusinessValidationError(Exception):
    """Исключение для бизнес-валидации"""

    def __init__(self, message: str, details: dict = None):  # type: ignore
        self.message = message
        self.details = details or {}
        super().__init__(message)


async def psycopg2_exception_handler(request: Request, exc: psycopg2.Error):
    """Handle psycopg2 database errors"""

    # Foreign key violation
    if isinstance(exc, psycopg2.errors.ForeignKeyViolation):
        error_msg = str(exc).split("\n")[0]
        logger.warning(
            "Foreign key violation",
            extra={
                "error_type": "foreign_key_violation",
                "path": request.url.path,
                "method": request.method,
                "detail": error_msg,
            },
        )
        error = BaseError(type="foreign_key_violation", message=error_msg)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error.model_dump())

    # Unique constraint violation
    if isinstance(exc, psycopg2.errors.UniqueViolation):
        error_msg = str(exc).split("\n")[0]
        logger.warning(
            "Unique constraint violation",
            extra={
                "error_type": "unique_violation",
                "path": request.url.path,
                "method": request.method,
                "detail": error_msg,
            },
        )
        error = BaseError(type="unique_violation", message=error_msg)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error.model_dump())

    # Not null violation
    if isinstance(exc, psycopg2.errors.NotNullViolation):
        error_msg = str(exc).split("\n")[0]
        logger.warning(
            "Not null constraint violation",
            extra={
                "error_type": "not_null_violation",
                "path": request.url.path,
                "method": request.method,
                "detail": error_msg,
            },
        )
        error = BaseError(type="not_null_violation", message=error_msg)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error.model_dump())

    # Check constraint violation
    if isinstance(exc, psycopg2.errors.CheckViolation):
        error_msg = str(exc).split("\n")[0]
        logger.warning(
            "Check constraint violation",
            extra={
                "error_type": "check_violation",
                "path": request.url.path,
                "method": request.method,
                "detail": error_msg,
            },
        )
        error = BaseError(type="check_violation", message=error_msg)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error.model_dump())

    # Generic database error
    logger.error(
        "Unexpected database error",
        extra={
            "error_type": "database_error",
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
        },
        exc_info=True,
    )
    error = BaseError(type="database_error", message="An unexpected database error occurred")
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error.model_dump())


async def asyncpg_exception_handler(request: Request, exc: asyncpg.PostgresError):
    """Handle asyncpg database errors"""

    # Foreign key violation
    if isinstance(exc, asyncpg.ForeignKeyViolationError):
        error_msg = str(exc).split("\n")[0]
        logger.warning(
            "Foreign key violation",
            extra={
                "error_type": "foreign_key_violation",
                "path": request.url.path,
                "method": request.method,
                "detail": error_msg,
            },
        )
        error = BaseError(type="foreign_key_violation", message=error_msg)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error.model_dump())

    # Unique constraint violation
    if isinstance(exc, asyncpg.UniqueViolationError):
        error_msg = str(exc).split("\n")[0]
        logger.warning(
            "Unique constraint violation",
            extra={
                "error_type": "unique_violation",
                "path": request.url.path,
                "method": request.method,
                "detail": error_msg,
            },
        )
        error = BaseError(type="unique_violation", message=error_msg)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error.model_dump())

    # Not null violation
    if isinstance(exc, asyncpg.NotNullViolationError):
        error_msg = str(exc).split("\n")[0]
        logger.warning(
            "Not null constraint violation",
            extra={
                "error_type": "not_null_violation",
                "path": request.url.path,
                "method": request.method,
                "detail": error_msg,
            },
        )
        error = BaseError(type="not_null_violation", message=error_msg)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error.model_dump())

    # Check constraint violation
    if isinstance(exc, asyncpg.CheckViolationError):
        error_msg = str(exc).split("\n")[0]
        logger.warning(
            "Check constraint violation",
            extra={
                "error_type": "check_violation",
                "path": request.url.path,
                "method": request.method,
                "detail": error_msg,
            },
        )
        error = BaseError(type="check_violation", message=error_msg)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error.model_dump())

    # Generic database error
    logger.error(
        "Unexpected database error",
        extra={
            "error_type": "database_error",
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
        },
        exc_info=True,
    )
    error = BaseError(type="database_error", message="An unexpected database error occurred")
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error.model_dump())


async def validation_exception_handler(request: Request, exc: RequestValidationError):

    logger.error(
        "Request Validation Error",
        extra={
            "error_type": "request_validation_error",
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
            "request_body": request.body(),
        },
        exc_info=True,
    )

    message = "\n".join((f"Field: {error['loc']}, Error: {error['msg']}" for error in exc.errors()))

    error = BaseError(type="request_validation_error", message=message)

    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=error.model_dump())
