from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

from app.config import settings

# Create the async engine that manages the connection pool to PostgreSQL.
# echo=True logs all SQL statements — helpful during development.
engine = create_async_engine(settings.DATABASE_URL, echo=True)

# Session factory — each call produces a new AsyncSession bound to the engine.
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """
    Initializes database tables defined in SQLAlchemy models if they do not exist.
    """
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """
    FastAPI dependency that provides a database session.

    Usage in a route:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...

    The session is automatically closed when the request finishes.
    """
    async with async_session_maker() as session:
        yield session
