import uuid

from pydantic import BaseModel


class MeRead(BaseModel):
    """The signed-in user and their business; ``business_id`` is None until they create one."""

    id: uuid.UUID
    email: str | None
    business_id: uuid.UUID | None
    role: str | None
