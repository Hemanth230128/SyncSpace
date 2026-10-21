from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

from app.config import settings

# Create the async engine with optimized connection pooling for Neon PostgreSQL.
# echo=False prevents console stdout bottleneck.
# pool_pre_ping=False avoids extra high-latency SELECT 1 pings across the internet on every query.
# pool_recycle=300 safely recycles idle connections before Neon's 5-minute timeout.
# statement_cache_size=0 is required for PgBouncer / Neon transaction poolers.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=False,
    pool_recycle=300,
    connect_args={"statement_cache_size": 0},
)

# Session factory — each call produces a new AsyncSession bound to the engine.
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """
    Initializes database tables defined in SQLAlchemy models if they do not exist.
    Also ensures the pgvector extension is enabled.
    """
    from sqlalchemy import text
    from app.models import Base

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
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
