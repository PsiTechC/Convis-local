from pydantic import BaseModel, Field
from typing import Optional, Literal

AllowedProvider = Literal['openai', 'anthropic', 'azure_openai', 'google', 'custom']


class APIKeyCreate(BaseModel):
    user_id: str
    provider: AllowedProvider = Field(..., description="AI provider for the API key")
    label: str = Field(..., min_length=2, max_length=100)
    api_key: str = Field(..., min_length=8, description="Raw API key input")
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional notes to help distinguish this key",
    )


class APIKeyUpdate(BaseModel):
    provider: Optional[AllowedProvider] = None
    label: Optional[str] = Field(None, min_length=2, max_length=100)
    api_key: Optional[str] = Field(None, min_length=8)
    description: Optional[str] = Field(None, max_length=500)


class APIKeyResponse(BaseModel):
    id: str
    user_id: str
    provider: AllowedProvider
    label: str
    description: Optional[str] = None
    last_four: str
    created_at: str
    updated_at: str


class APIKeyListResponse(BaseModel):
    keys: list[APIKeyResponse]
    total: int
