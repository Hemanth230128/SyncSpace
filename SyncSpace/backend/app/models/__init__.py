from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.user import User
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.join_request import JoinRequest
from app.models.message import Message
from app.models.document import Document, DocumentChunk

__all__ = [
    "Base",
    "User",
    "Group",
    "GroupMember",
    "JoinRequest",
    "Message",
    "Document",
    "DocumentChunk",
]

