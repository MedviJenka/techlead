from pydantic import BaseModel, Field


class CRMSchema(BaseModel):
    confidence_level: float = Field(..., ge=0, le=100, description='confidence level')
