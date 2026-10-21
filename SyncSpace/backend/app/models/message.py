from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class Message(Base):
    """
    SQLAlchemy model representing a chat message within a group.

    Columns:
        id: Auto-incrementing integer primary key
        group_id: Foreign key referencing the group this message belongs to
        user_id: Foreign key referencing the user who sent this message
        content: The text content of the message
        created_at: UTC timestamp when the message was sent
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Composite index for fast chronological message retrieval within a group
    __table_args__ = (
        Index("ix_messages_group_id_created_at", "group_id", "created_at"),
    )

    # Relationships
    group = relationship("Group", backref="messages")
    user = relationship("User", backref="messages")
