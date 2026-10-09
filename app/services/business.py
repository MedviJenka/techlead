import uuid
from dataclasses import dataclass
from typing import Any

from postgrest.exceptions import APIError

from app.core.errors import ConflictError, NotFoundError
from app.core.logger import Logger
from app.models import Business
from app.repositories import BusinessRepository
from app.schemas import BusinessCreate
from app.schemas.configuration import (
    BusinessConfiguration,
    BusinessSettingsUpdate,
    CustomFieldDefinition,
    stored_definitions,
)

logger = Logger(__name__)

UNIQUE_VIOLATION = "23505"


def _slug_taken(slug: str) -> ConflictError:
    return ConflictError(f"Business slug '{slug}' is already taken")


async def require_business(repository: BusinessRepository, business_id: uuid.UUID) -> Business:
    """The business, or ``NotFoundError``. Every tenant-scoped service checks this first (unknown tenant -> 404)."""
    business = await repository.get(business_id)
    if business is None:
        raise NotFoundError(f"Business {business_id} not found")
    return business


@dataclass(frozen=True)
class BusinessSettings:
    """The parsed deterministic settings of one business (defaults where the stored JSON does not parse)."""

    configuration: BusinessConfiguration
    custom_fields: list[CustomFieldDefinition]
    # New leads are queued for AI analysis (NewLeadFlow) unless the business turned it off.
    auto_analyze: bool = True

    @classmethod
    def of(cls, business: Business) -> "BusinessSettings":
        return cls(
            BusinessConfiguration.from_stored(business.configuration),
            stored_definitions(business.custom_field_definitions),
            business.ai_configuration.get("auto_analyze") is not False,
        )


def _definitions_json(definitions: list[CustomFieldDefinition]) -> list[dict[str, Any]]:
    return [definition.model_dump(mode="json") for definition in definitions]


def _to_values(data: BusinessCreate) -> dict[str, Any]:
    """Explicit field mapping: only these columns are client-settable (no mass assignment)."""
    return {
        "name": data.name,
        "slug": data.slug,
        "industry": data.industry,
        "timezone": data.timezone,
        "configuration": data.configuration.model_dump(mode="json"),
        "custom_field_definitions": _definitions_json(data.custom_field_definitions),
        "ai_configuration": data.ai_configuration.to_ai_configuration().model_dump(mode="json"),
    }


class BusinessService:
    def __init__(self, repository: BusinessRepository) -> None:
        self._repository = repository

    async def create(self, data: BusinessCreate) -> Business:
        if await self._repository.get_by_slug(data.slug) is not None:
            logger.fire("business_slug_taken", level="warning", slug=data.slug)
            raise _slug_taken(data.slug)
        try:
            business = await self._repository.add(_to_values(data))
        except APIError as exc:
            if exc.code != UNIQUE_VIOLATION:
                raise
            raise _slug_taken(data.slug) from exc  # lost a race with a concurrent create of the same slug
        logger.fire("business_created", business_id=str(business.id), slug=business.slug)
        return business

    async def get(self, business_id: uuid.UUID) -> Business:
        return await require_business(self._repository, business_id)

    async def update_settings(self, business_id: uuid.UUID, data: BusinessSettingsUpdate) -> Business:
        """Replace the configuration and custom field definitions. Stored lead scores change only on rescore."""
        values = {
            "configuration": data.configuration.model_dump(mode="json"),
            "custom_field_definitions": _definitions_json(data.custom_field_definitions),
        }
        business = await self._repository.update(business_id, values)
        if business is None:
            raise NotFoundError(f"Business {business_id} not found")
        logger.fire(
            "business_settings_updated",
            business_id=str(business_id),
            custom_fields=len(data.custom_field_definitions),
        )
        return business
