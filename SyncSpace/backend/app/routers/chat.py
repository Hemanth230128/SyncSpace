from datetime import datetime, timezone
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connection_manager import manager
from app.database import async_session_maker, get_db
from app.dependencies import get_current_user
from app.models import Group, GroupMember, Message, User
from app.schemas import MessageResponse
from app.security import decode_access_token

router = APIRouter(tags=["Chat"])


# ---------------------------------------------------------------------------
# 1. GET /api/groups/{group_id}/messages — Retrieve Message History
# ---------------------------------------------------------------------------
@router.get("/api/groups/{group_id}/messages", response_model=list[MessageResponse])
@router.get("/groups/{group_id}/messages", response_model=list[MessageResponse], include_in_schema=False)
async def get_group_messages(
    group_id: int,
    limit: int = Query(50, ge=1, le=100, description="Maximum number of messages to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves message history for a group in chronological order in a single query.
    """
    stmt = (
        select(
            GroupMember.role.label("member_role"),
            Message.id,
            Message.group_id,
            Message.user_id,
            User.username,
            Message.content,
            Message.created_at,
        )
        .select_from(GroupMember)
        .outerjoin(Message, Message.group_id == GroupMember.group_id)
        .outerjoin(User, Message.user_id == User.id)
        .where(
            and_(
                GroupMember.group_id == group_id,
                GroupMember.user_id == current_user.id,
            )
        )
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        # Check if group even exists to return proper 404 or 403
        group_exists = await db.scalar(select(Group.id).where(Group.id == group_id))
        if not group_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # If first row has no message id, the group currently has 0 messages
    if rows[0].id is None:
        return []

    return [
        MessageResponse(
            id=row.id,
            group_id=row.group_id,
            user_id=row.user_id,
            username=row.username,
            content=row.content,
            created_at=row.created_at,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 2. WEBSOCKET /ws/groups/{group_id} — Real-Time Group Chat
# ---------------------------------------------------------------------------
@router.websocket("/ws/groups/{group_id}")
async def websocket_group_chat(
    websocket: WebSocket,
    group_id: int,
    token: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for real-time messaging within a specific group.
    """
    # 1. Accept connection immediately so the browser handshake resolves in <1ms
    await websocket.accept()

    # 2. Authenticate token
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        return

    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
        return

    user_id_raw = payload.get("sub")
    if not user_id_raw:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing user ID in token")
        return

    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid user ID format in token")
        return

    authenticated_username = payload.get("username")

    # 3. Fast single-table authorization: check group membership
    async with async_session_maker() as db:
        role = await db.scalar(
            select(GroupMember.role).where(
                and_(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == user_id,
                )
            )
        )

        if not role:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="User is not an authorized member of this group",
            )
            return

        if not authenticated_username:
            user_row = await db.scalar(select(User.username).where(User.id == user_id))
            authenticated_username = user_row or f"User #{user_id}"

    authenticated_user_id = user_id

    # 4. Register connection with ConnectionManager
    await manager.connect(group_id, websocket)

    try:
        # 4. Message loop
        while True:
            raw_text = await websocket.receive_text()

            # Parse message content from JSON {"content": "..."} or raw string
            content = ""
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, dict) and "content" in parsed:
                    content = str(parsed["content"]).strip()
                elif isinstance(parsed, str):
                    content = parsed.strip()
            except (json.JSONDecodeError, Exception):
                content = raw_text.strip()

            # Reject empty messages
            if not content:
                await websocket.send_json({"error": "Message content cannot be empty"})
                continue

            # Limit max length
            if len(content) > 5000:
                await websocket.send_json({"error": "Message content exceeds maximum length of 5000 characters"})
                continue

            # Fast single-query persistence with pre-computed timestamp
            now_utc = datetime.now(timezone.utc)
            async with async_session_maker() as db:
                new_msg = Message(
                    group_id=group_id,
                    user_id=authenticated_user_id,
                    content=content,
                    created_at=now_utc,
                )
                db.add(new_msg)
                await db.flush()  # Instantly retrieves generated new_msg.id
                msg_id = new_msg.id
                await db.commit()

            # Format payload for instant broadcast
            broadcast_payload = {
                "id": msg_id,
                "group_id": group_id,
                "user_id": authenticated_user_id,
                "username": authenticated_username,
                "content": content,
                "created_at": now_utc.isoformat(),
            }

            # Broadcast concurrently in parallel to all members in room
            await manager.broadcast(group_id, broadcast_payload)

    except WebSocketDisconnect:
        # Normal disconnect when client closes window, reloads, or navigates away
        pass
    except Exception:
        # Prevent server crashes on socket I/O errors
        pass
    finally:
        # Clean up connection
        manager.disconnect(group_id, websocket)
