from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class JoinRequest(Base):
    """
    Tracks a user's request to join a group.

    Columns:
        id: Auto-incrementing primary key
        user_id: FK to users.id — indexed
        group_id: FK to groups.id — indexed
        status: PENDING, APPROVED, or REJECTED
        created_at: UTC timestamp when the request was created
    """

    __tablename__ = "join_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_join_requests_group_status", "group_id", "status"),
        Index("ix_join_requests_user_group_status", "user_id", "group_id", "status"),
    )

    # Relationships — removed lazy="selectin" to prevent query amplification
    user = relationship("User", backref="join_requests")
    group = relationship("Group", back_populates="join_requests")
