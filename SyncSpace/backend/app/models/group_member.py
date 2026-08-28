from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class GroupMember(Base):
    """
    Association table implementing the many-to-many relationship between users and groups.

    Each row represents: "User X is a member of Group Y with Role Z".

    The composite primary key (user_id, group_id) prevents duplicate memberships —
    a user can only appear once per group.

    Columns:
        user_id: FK to users.id (part of composite PK)
        group_id: FK to groups.id (part of composite PK)
        role: Either 'ADMIN' or 'MEMBER'
        joined_at: UTC timestamp when the user joined the group
    """

    __tablename__ = "group_members"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="MEMBER")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user = relationship("User", backref="group_memberships", lazy="selectin")
    group = relationship("Group", back_populates="members", lazy="selectin")
