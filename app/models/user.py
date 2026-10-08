import uuid
from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    """A `users` row (db/002_users.sql): a person's membership in one business. ``id`` is the Supabase Auth id."""

    id: uuid.UUID
    business_id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
