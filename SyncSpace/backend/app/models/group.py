from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class Group(Base):
    """
    SQLAlchemy model representing a user-created group.

    Columns:
        id: Auto-incrementing integer primary key
        name: Display name for the group
        created_by: Foreign key referencing the user who created this group
        created_at: UTC timestamp when the group was created
    """

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships — without lazy="selectin" to prevent recursive cascading queries
    creator = relationship("User", backref="created_groups")
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    join_requests = relationship("JoinRequest", back_populates="group", cascade="all, delete-orphan")
