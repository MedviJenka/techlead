"""Typed rows of the Supabase tables. The tables themselves are defined in `db/*.sql`; keep both in sync."""

from app.models.activity import Activity
from app.models.business import Business
from app.models.lead import Lead
from app.models.user import User

__all__ = ["Activity", "Business", "Lead", "User"]
