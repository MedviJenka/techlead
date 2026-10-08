from datetime import UTC, datetime


def utc_now() -> datetime:
    """FastAPI dependency for the request's current time; tests override it with a fixed clock."""
    return datetime.now(UTC)
