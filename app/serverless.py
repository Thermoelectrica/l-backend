import logging

from mangum import Mangum  # ASGI adapter for serverless

from app.main import app

# Logging is already initialized in app.main
logger = logging.getLogger(__name__)

# Mangum adapts FastAPI to event format
# Configure Mangum with explicit lifespan handling for serverless
# Set lifespan="off" to disable FastAPI lifespan events in serverless environment
# This prevents connection pool initialization issues in Lambda
lambda_handler = Mangum(
    app,
    lifespan="off",  # Disable lifespan for serverless (connection pooling handled per invocation)
)


def handler(event, context):
    try:
        return lambda_handler(event, context)
    except Exception as e:
        logger.error(
            "Lambda invocation failed",
            extra={"request_id": context.request_id, "error": str(e)},
            exc_info=True,
        )
        raise
