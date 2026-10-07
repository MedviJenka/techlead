from typing import Self

from crewai.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from ai.ports import LeadReadService, NotFoundError


class NoArguments(BaseModel):
    """Tool takes no arguments."""


class BusinessScopedTool(BaseTool):
    """Read-only tool bound to one business at construction time.

    The business id is never a tool argument, so an agent cannot reach another tenant's data
    no matter what the prompt says.
    """

    _service: LeadReadService = PrivateAttr()
    _business_id: str = PrivateAttr()

    @classmethod
    def bind(cls, service: LeadReadService, business_id: str) -> Self:
        tool = cls()
        tool._service = service
        tool._business_id = business_id
        return tool

    @property
    def business_id(self) -> str:
        return self._business_id

    @staticmethod
    def not_found(error: NotFoundError) -> str:
        return f"ERROR: {error}. Do not guess; continue with the information you have."
