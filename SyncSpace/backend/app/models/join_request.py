from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class JoinRequest(Base):
    """
    Tracks a user's request to join a group.

    Workflow:
        1. User creates a join request → status = PENDING
        2. Group admin reviews:
           - Approve → status = APPROVED, GroupMember row created
           - Reject  → status = REJECTED, no membership created

    Duplicate pending requests for the same (user_id, group_id) are
    prevented in application logic before insertion.

    Columns:
        id: Auto-incrementing primary key
        user_id: FK to users.id — the user requesting to join
        group_id: FK to groups.id — the target group
        status: PENDING, APPROVED, or REJECTED
        created_at: UTC timestamp when the request was created
    """

    __tablename__ = "join_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user = relationship("User", backref="join_requests", lazy="selectin")
    group = relationship("Group", back_populates="join_requests", lazy="selectin")
