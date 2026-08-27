from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    """
    Schema for user signup requests.
    Validates that username and password meet minimum length requirements.
    """

    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    password: str = Field(..., min_length=6, max_length=100, description="Plaintext password to hash")


class UserLogin(BaseModel):
    """
    Schema for user login requests.
    """

    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class UserResponse(BaseModel):
    """
    Public user representation returned to clients.
    NEVER includes password or password_hash.
    """

    id: int
    username: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """
    Response schema returning a signed JWT access token.
    """

    access_token: str
    token_type: str = "bearer"
