from datetime import datetime
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class User(Base):
    """
    SQLAlchemy model representing a registered user in the application.

    Columns:
        id: Auto-incrementing integer primary key
        username: Unique username, indexed for quick lookups
        password_hash: Securely hashed password (bcrypt)
        created_at: UTC timestamp when the user registered
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
