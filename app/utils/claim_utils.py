"""Utility functions for plant claim management"""

from datetime import datetime, time, timedelta, timezone
from typing import Optional


def is_claim_stale(claimed_at: Optional[datetime]) -> bool:
    """
    Check if claim is stale. Claim becomes stale at 3:00 AM Moscow time (UTC+3) every day.
    Stale claims persist but can be overridden by other users.

    Args:
        claimed_at: The timestamp when the plant was claimed

    Returns:
        True if claim is stale (can be overridden), False otherwise
    """
    if claimed_at is None:
        return True

    # Get current time in UTC
    now_utc = datetime.now(timezone.utc)

    # Convert claimed_at to UTC if it has timezone info, otherwise assume UTC
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=timezone.utc)

    # Calculate today's 3:00 AM Moscow time (00:00 UTC)
    # Moscow is UTC+3, so 3:00 AM Moscow = 00:00 UTC
    today_3am_moscow_utc = datetime.combine(now_utc.date(), time(0, 0), tzinfo=timezone.utc)

    # Find the last 3:00 AM that has already passed
    last_3am = today_3am_moscow_utc
    if now_utc < today_3am_moscow_utc:
        last_3am = today_3am_moscow_utc - timedelta(days=1)

    # Claim is stale if the last 3:00 AM occurred after the claim time
    return claimed_at < last_3am
