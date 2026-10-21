from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import TokenResponse, UserCreate, UserLogin, UserResponse
from app.security import (
    create_access_token,
    async_hash_password,
    async_verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Registers a new user account with a unique username and securely hashed password.
    """
    # 1. Check if the username is already taken
    existing_user_query = await db.execute(
        select(User).where(User.username == user_in.username.strip())
    )
    if existing_user_query.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    # 2. Hash the plaintext password non-blockingly
    hashed_pwd = await async_hash_password(user_in.password)

    # 3. Create and persist the user in PostgreSQL
    new_user = User(
        username=user_in.username.strip(),
        password_hash=hashed_pwd,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Authenticates a user and issues a signed JWT access token.
    """
    # 1. Retrieve the user by username
    user_query = await db.execute(
        select(User).where(User.username == credentials.username.strip())
    )
    user = user_query.scalar_one_or_none()

    # 2. Verify existence and password hash non-blockingly
    if user is None or not (await async_verify_password(credentials.password, user.password_hash)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Generate signed JWT access token containing user identity
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
        }
    )

    return TokenResponse(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Protected endpoint to retrieve the currently authenticated user's profile.
    Requires Authorization: Bearer <token>
    """
    return current_user
