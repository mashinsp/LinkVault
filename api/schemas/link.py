from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class LinkCreate(BaseModel):
    url: AnyHttpUrl
    custom_shortcode: str | None = Field(None, min_length=3, max_length=12, pattern=r"^[a-zA-Z0-9_-]+$")
    expires_at: datetime | None = None

    @field_validator("custom_shortcode")
    @classmethod
    def shortcode_not_reserved(cls, v: str | None) -> str | None:
        reserved = {"api", "admin", "health", "static", "docs"}
        if v and v.lower() in reserved:
            raise ValueError(f"'{v}' is a reserved shortcode")
        return v


class LinkResponse(BaseModel):
    id: UUID
    shortcode: str
    original_url: str
    short_url: str
    click_count: int
    is_active: bool
    created_at: datetime
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class LinkStats(BaseModel):
    shortcode: str
    original_url: str
    click_count: int
    created_at: datetime
    expires_at: datetime | None
    is_active: bool