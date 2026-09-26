"""Request and response models of the HTTP API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

MAX_URL_LENGTH = 2048


class ErrorResponse(BaseModel):
    detail: str


class SiteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200, examples=["Example"])
    # HttpUrl accepts http and https only, and normalizes the URL
    # (lowercase host, "/" path), so equivalent URLs are detected as duplicates.
    url: HttpUrl = Field(examples=["https://example.com/"])

    @field_validator("url")
    @classmethod
    def check_url(cls, url: HttpUrl) -> HttpUrl:
        # Never store credentials in the database.
        if url.username or url.password:
            raise ValueError("URL must not contain credentials")
        if len(str(url)) > MAX_URL_LENGTH:
            raise ValueError(f"URL must be at most {MAX_URL_LENGTH} characters")
        return url


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: HttpUrl
    created_at: datetime
