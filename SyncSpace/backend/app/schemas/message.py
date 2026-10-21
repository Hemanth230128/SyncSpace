from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class MessageSend(BaseModel):
    """
    Schema for validating incoming chat messages sent via WebSocket or REST.
    """

    content: str = Field(..., min_length=1, max_length=5000, description="Message text content")


class MessageResponse(BaseModel):
    """
    Public message representation returned in REST responses and WebSocket broadcasts.
    """

    id: int
    group_id: int
    user_id: int
    username: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
