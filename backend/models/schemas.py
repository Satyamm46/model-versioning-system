"""Request bodies (validated automatically by Pydantic)."""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ModelCreate(_Base):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    model_type: str = Field("", max_length=50)
    created_by: str = Field("anonymous", min_length=1, max_length=50)


class PromoteRequest(_Base):
    performed_by: str = Field("anonymous", min_length=1, max_length=50)


class RollbackRequest(_Base):
    performed_by: str = Field("anonymous", min_length=1, max_length=50)
    reason: str = Field("", max_length=300)
    to_version: Optional[int] = Field(None, ge=1)


class StatusUpdate(_Base):
    status: str
