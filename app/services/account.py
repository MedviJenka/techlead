"""Who may see which business. Every signed-in user belongs to at most one business (a `users` row)."""

import logging
import uuid

from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.core.auth import AuthUser
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.models import Business
from app.repositories import BusinessRepository, UserRepository
from app.schemas import BusinessCreate
from app.schemas.account import MeRead
from app.services.business import UNIQUE_VIOLATION, BusinessService

logger = logging.getLogger(__name__)

OWNER_ROLE = "owner"


def _already_member() -> ConflictError:
    return ConflictError("You already belong to a business")


class AccountService:
    def __init__(self, db: AsyncClient) -> None:
        self.users = UserRepository(db)
        self.business_repository = BusinessRepository(db)
        self.businesses = BusinessService(self.business_repository)

    async def me(self, user: AuthUser) -> MeRead:
        member = await self.users.get(user.id)
        return MeRead(
            id=user.id,
            email=user.email,
            business_id=member.business_id if member else None,
            role=member.role if member else None,
        )

    async def require_access(self, user: AuthUser, business_id: uuid.UUID) -> None:
        """404 (not 403) for another business, so its existence is not revealed."""
        member = await self.users.get(user.id)
        if member is None or not member.is_active or member.business_id != business_id:
            raise NotFoundError(f"Business {business_id} not found")

    async def create_business(self, user: AuthUser, data: BusinessCreate) -> Business:
        """Create the business with ``user`` as its owner. A user belongs to one business only."""
        if user.email is None:
            raise UnprocessableError("Your account has no email address")
        if await self.users.get(user.id) is not None:
            raise _already_member()
        business = await self.businesses.create(data)
        owner = {"id": user.id, "business_id": business.id, "email": user.email, "full_name": user.name}
        try:
            await self.users.add(owner | {"role": OWNER_ROLE})
        except Exception as exc:
            # Two requests, not one transaction: remove the business so no ownerless one is left behind.
            await self.business_repository.delete(business.id)
            if isinstance(exc, APIError) and exc.code == UNIQUE_VIOLATION:
                raise _already_member() from exc  # lost a race with a concurrent create by the same user
            raise
        logger.info("business_owner_added", extra={"business_id": str(business.id), "user_id": str(user.id)})
        return business
