from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Group, GroupMember, JoinRequest, User
from app.schemas import (
    GroupCreate,
    GroupListItem,
    GroupMemberResponse,
    GroupResponse,
    JoinRequestResponse,
)

router = APIRouter(prefix="/api/groups", tags=["Groups"])


# ---------------------------------------------------------------------------
# Helper: look up a user's membership role for a given group (fast column query)
# ---------------------------------------------------------------------------
async def _get_membership_role(db: AsyncSession, user_id: int, group_id: int) -> str | None:
    """Returns the user's role ('ADMIN' or 'MEMBER') if a member, else None."""
    result = await db.execute(
        select(GroupMember.role).where(
            and_(GroupMember.user_id == user_id, GroupMember.group_id == group_id)
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# 1. POST /api/groups — Create a new group
# ---------------------------------------------------------------------------
@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_in: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a new group and automatically makes the creator an ADMIN member.
    """
    # 1. Create the group
    new_group = Group(
        name=group_in.name.strip(),
        description=group_in.description.strip() if group_in.description else None,
        created_by=current_user.id,
    )
    db.add(new_group)
    await db.flush()  # Assigns new_group.id and default values

    # 2. Insert creator as ADMIN member
    admin_member = GroupMember(
        user_id=current_user.id,
        group_id=new_group.id,
        role="ADMIN",
    )
    db.add(admin_member)

    await db.commit()

    return GroupResponse(
        id=new_group.id,
        name=new_group.name,
        description=new_group.description,
        created_by=new_group.created_by,
        creator_username=current_user.username,
        created_at=new_group.created_at,
        user_role="ADMIN",
    )


# ---------------------------------------------------------------------------
# 2. GET /api/groups — List all groups (with membership status for current user)
# ---------------------------------------------------------------------------
@router.get("", response_model=list[GroupListItem])
async def list_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all groups with the current user's membership/request status for each in a single fast query.
    """
    query = (
        select(
            Group.id,
            Group.name,
            Group.description,
            Group.created_by,
            Group.created_at,
            User.username.label("creator_username"),
            GroupMember.role.label("user_role"),
            JoinRequest.status.label("request_status"),
        )
        .join(User, Group.created_by == User.id)
        .outerjoin(
            GroupMember,
            and_(
                GroupMember.group_id == Group.id,
                GroupMember.user_id == current_user.id,
            ),
        )
        .outerjoin(
            JoinRequest,
            and_(
                JoinRequest.group_id == Group.id,
                JoinRequest.user_id == current_user.id,
                JoinRequest.status == "PENDING",
            ),
        )
        .order_by(Group.created_at.desc())
    )

    result = await db.execute(query)

    items = []
    for row in result.all():
        membership_status = row.user_role or row.request_status or None
        items.append(
            GroupListItem(
                id=row.id,
                name=row.name,
                description=row.description,
                created_by=row.created_by,
                creator_username=row.creator_username,
                created_at=row.created_at,
                membership_status=membership_status,
            )
        )

    return items


# ---------------------------------------------------------------------------
# 3. GET /api/groups/{group_id} — Get group details (members only)
# ---------------------------------------------------------------------------
@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns group details. Only accessible by members of the group.
    """
    query = (
        select(
            Group.id,
            Group.name,
            Group.description,
            Group.created_by,
            Group.created_at,
            User.username.label("creator_username"),
            GroupMember.role.label("user_role"),
        )
        .join(User, Group.created_by == User.id)
        .outerjoin(
            GroupMember,
            and_(
                GroupMember.group_id == Group.id,
                GroupMember.user_id == current_user.id,
            ),
        )
        .where(Group.id == group_id)
    )

    result = await db.execute(query)
    row = result.one_or_none()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    if row.user_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    return GroupResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        created_by=row.created_by,
        creator_username=row.creator_username,
        created_at=row.created_at,
        user_role=row.user_role,
    )


# ---------------------------------------------------------------------------
# 4. POST /api/groups/{group_id}/join — Request to join a group
# ---------------------------------------------------------------------------
@router.post("/{group_id}/join", response_model=JoinRequestResponse, status_code=status.HTTP_201_CREATED)
async def request_to_join(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a PENDING join request. Fails if user is already a member
    or already has a pending request.
    """
    group_check = await db.execute(
        select(
            Group.name,
            GroupMember.role.label("member_role"),
            JoinRequest.status.label("pending_status"),
        )
        .outerjoin(
            GroupMember,
            and_(
                GroupMember.group_id == Group.id,
                GroupMember.user_id == current_user.id,
            ),
        )
        .outerjoin(
            JoinRequest,
            and_(
                JoinRequest.group_id == Group.id,
                JoinRequest.user_id == current_user.id,
                JoinRequest.status == "PENDING",
            ),
        )
        .where(Group.id == group_id)
    )
    row = group_check.one_or_none()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    if row.member_role is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already a member of this group",
        )

    if row.pending_status is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending request for this group",
        )

    join_request = JoinRequest(
        user_id=current_user.id,
        group_id=group_id,
        status="PENDING",
    )
    db.add(join_request)
    await db.commit()

    return JoinRequestResponse(
        id=join_request.id,
        user_id=current_user.id,
        username=current_user.username,
        group_id=group_id,
        group_name=row.name,
        status="PENDING",
        created_at=join_request.created_at,
    )


# ---------------------------------------------------------------------------
# 5. GET /api/groups/{group_id}/requests — List pending join requests (admin only)
# ---------------------------------------------------------------------------
@router.get("/{group_id}/requests", response_model=list[JoinRequestResponse])
async def list_join_requests(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all PENDING join requests for a group. Only accessible by the group's ADMIN.
    """
    role = await _get_membership_role(db, current_user.id, group_id)
    if role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group admin can view join requests",
        )

    requests_result = await db.execute(
        select(
            JoinRequest.id,
            JoinRequest.user_id,
            JoinRequest.group_id,
            JoinRequest.status,
            JoinRequest.created_at,
            User.username,
            Group.name.label("group_name"),
        )
        .join(User, JoinRequest.user_id == User.id)
        .join(Group, JoinRequest.group_id == Group.id)
        .where(
            and_(
                JoinRequest.group_id == group_id,
                JoinRequest.status == "PENDING",
            )
        )
        .order_by(JoinRequest.created_at.asc())
    )

    items = []
    for row in requests_result.all():
        items.append(
            JoinRequestResponse(
                id=row.id,
                user_id=row.user_id,
                username=row.username,
                group_id=row.group_id,
                group_name=row.group_name,
                status=row.status,
                created_at=row.created_at,
            )
        )

    return items


# ---------------------------------------------------------------------------
# 6. POST /api/groups/{group_id}/requests/{request_id}/approve — Approve (admin only)
# ---------------------------------------------------------------------------
@router.post("/{group_id}/requests/{request_id}/approve", response_model=JoinRequestResponse)
async def approve_request(
    group_id: int,
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Approves a pending join request:
    1. Updates status to APPROVED
    2. Creates a GroupMember row with MEMBER role
    """
    role = await _get_membership_role(db, current_user.id, group_id)
    if role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group admin can approve requests",
        )

    req_result = await db.execute(
        select(JoinRequest, User.username, Group.name.label("group_name"))
        .join(User, JoinRequest.user_id == User.id)
        .join(Group, JoinRequest.group_id == Group.id)
        .where(
            and_(JoinRequest.id == request_id, JoinRequest.group_id == group_id)
        )
    )
    row = req_result.one_or_none()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")

    join_request, username, group_name = row

    if join_request.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request has already been {join_request.status.lower()}",
        )

    # 1. Update request status
    join_request.status = "APPROVED"

    # 2. Create membership
    new_member = GroupMember(
        user_id=join_request.user_id,
        group_id=group_id,
        role="MEMBER",
    )
    db.add(new_member)

    await db.commit()

    return JoinRequestResponse(
        id=join_request.id,
        user_id=join_request.user_id,
        username=username,
        group_id=group_id,
        group_name=group_name,
        status=join_request.status,
        created_at=join_request.created_at,
    )


# ---------------------------------------------------------------------------
# 7. POST /api/groups/{group_id}/requests/{request_id}/reject — Reject (admin only)
# ---------------------------------------------------------------------------
@router.post("/{group_id}/requests/{request_id}/reject", response_model=JoinRequestResponse)
async def reject_request(
    group_id: int,
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rejects a pending join request. Does NOT create a membership row.
    """
    role = await _get_membership_role(db, current_user.id, group_id)
    if role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group admin can reject requests",
        )

    req_result = await db.execute(
        select(JoinRequest, User.username, Group.name.label("group_name"))
        .join(User, JoinRequest.user_id == User.id)
        .join(Group, JoinRequest.group_id == Group.id)
        .where(
            and_(JoinRequest.id == request_id, JoinRequest.group_id == group_id)
        )
    )
    row = req_result.one_or_none()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")

    join_request, username, group_name = row

    if join_request.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request has already been {join_request.status.lower()}",
        )

    join_request.status = "REJECTED"
    await db.commit()

    return JoinRequestResponse(
        id=join_request.id,
        user_id=join_request.user_id,
        username=username,
        group_id=group_id,
        group_name=group_name,
        status=join_request.status,
        created_at=join_request.created_at,
    )


# ---------------------------------------------------------------------------
# 8. GET /api/groups/{group_id}/members — List group members (members only)
# ---------------------------------------------------------------------------
@router.get("/{group_id}/members", response_model=list[GroupMemberResponse])
async def list_members(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all members of a group. Only accessible by existing members.
    """
    role = await _get_membership_role(db, current_user.id, group_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    members_result = await db.execute(
        select(
            GroupMember.user_id,
            GroupMember.role,
            GroupMember.joined_at,
            User.username,
        )
        .join(User, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at.asc())
    )

    items = []
    for row in members_result.all():
        items.append(
            GroupMemberResponse(
                user_id=row.user_id,
                username=row.username,
                role=row.role,
                joined_at=row.joined_at,
            )
        )

    return items


# ---------------------------------------------------------------------------
# 9. DELETE /api/groups/{group_id}/leave — Leave a group
# ---------------------------------------------------------------------------
@router.delete("/{group_id}/leave", status_code=status.HTTP_200_OK)
async def leave_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Removes the current user from the group.
    An ADMIN cannot leave if they are the only admin.
    """
    membership_result = await db.execute(
        select(GroupMember).where(
            and_(GroupMember.user_id == current_user.id, GroupMember.group_id == group_id)
        )
    )
    membership = membership_result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    if membership.role == "ADMIN":
        other_admin_result = await db.execute(
            select(GroupMember.user_id).where(
                and_(
                    GroupMember.group_id == group_id,
                    GroupMember.role == "ADMIN",
                    GroupMember.user_id != current_user.id,
                )
            ).limit(1)
        )
        if other_admin_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You are the only admin. Transfer admin role or delete the group before leaving.",
            )

    await db.delete(membership)
    await db.commit()

    return {"detail": "You have left the group"}


# ---------------------------------------------------------------------------
# 10. DELETE /api/groups/{group_id} — Delete a group (admin only)
# ---------------------------------------------------------------------------
@router.delete("/{group_id}", status_code=status.HTTP_200_OK)
async def delete_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes a group and all associated members and join requests atomically.
    Only accessible by the group's ADMIN.
    """
    # 1. Verify group exists
    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()

    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    # 2. Verify admin role
    role = await _get_membership_role(db, current_user.id, group_id)
    if role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group admin can delete the group",
        )

    # 3. Delete group — cascade foreign keys safely remove group_members and join_requests
    await db.delete(group)
    await db.commit()

    return {"detail": f"Group '{group.name}' has been deleted"}
