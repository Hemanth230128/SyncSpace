from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    """
    Schema for creating a new group.
    Only requires a name — the creator is determined from the JWT.
    """

    name: str = Field(..., min_length=1, max_length=100, description="Group display name")


class GroupResponse(BaseModel):
    """
    Public group representation returned to clients.
    Includes the requesting user's role if they are a member.
    """

    id: int
    name: str
    created_by: int
    creator_username: str
    created_at: datetime
    user_role: Optional[str] = None  # ADMIN, MEMBER, or None if not a member

    model_config = ConfigDict(from_attributes=True)


class GroupListItem(BaseModel):
    """
    Schema for a group in the list-all-groups response.
    Shows the user's membership status alongside group info.
    """

    id: int
    name: str
    created_by: int
    creator_username: str
    created_at: datetime
    membership_status: Optional[str] = None  # "ADMIN", "MEMBER", "PENDING", or None

    model_config = ConfigDict(from_attributes=True)


class GroupMemberResponse(BaseModel):
    """
    Schema for a single member within a group.
    """

    user_id: int
    username: str
    role: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JoinRequestResponse(BaseModel):
    """
    Schema representing a join request.
    Includes the requesting user's username and the target group name
    for convenience in the admin review UI.
    """

    id: int
    user_id: int
    username: str
    group_id: int
    group_name: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
