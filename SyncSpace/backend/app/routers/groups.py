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
# Helper: look up a user's membership row for a given group
# ---------------------------------------------------------------------------
async def _get_membership(db: AsyncSession, user_id: int, group_id: int):
    """Returns the GroupMember row if the user is a member, else None."""
    result = await db.execute(
        select(GroupMember).where(
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
        created_by=current_user.id,
    )
    db.add(new_group)
    await db.flush()  # Assigns new_group.id without committing

    # 2. Insert creator as ADMIN member
    admin_member = GroupMember(
        user_id=current_user.id,
        group_id=new_group.id,
        role="ADMIN",
    )
    db.add(admin_member)

    await db.commit()
    await db.refresh(new_group)

    return GroupResponse(
        id=new_group.id,
        name=new_group.name,
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
    Returns all groups with the current user's membership/request status for each.
    """
    # Fetch all groups with their creators
    groups_result = await db.execute(
        select(Group, User.username)
        .join(User, Group.created_by == User.id)
    )
    groups_rows = groups_result.all()

    # Fetch user's memberships
    memberships_result = await db.execute(
        select(GroupMember.group_id, GroupMember.role)
        .where(GroupMember.user_id == current_user.id)
    )
    memberships = {row.group_id: row.role for row in memberships_result.all()}

    # Fetch user's pending join requests
    pending_result = await db.execute(
        select(JoinRequest.group_id)
        .where(
            and_(
                JoinRequest.user_id == current_user.id,
                JoinRequest.status == "PENDING",
            )
        )
    )
    pending_groups = {row.group_id for row in pending_result.all()}

    items = []
    for group, creator_username in groups_rows:
        if group.id in memberships:
            membership_status = memberships[group.id]  # "ADMIN" or "MEMBER"
        elif group.id in pending_groups:
            membership_status = "PENDING"
        else:
            membership_status = None

        items.append(
            GroupListItem(
                id=group.id,
                name=group.name,
                created_by=group.created_by,
                creator_username=creator_username,
                created_at=group.created_at,
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
    # Verify group exists
    group_result = await db.execute(
        select(Group, User.username)
        .join(User, Group.created_by == User.id)
        .where(Group.id == group_id)
    )
    row = group_result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    group, creator_username = row

    # Verify membership
    membership = await _get_membership(db, current_user.id, group_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    return GroupResponse(
        id=group.id,
        name=group.name,
        created_by=group.created_by,
        creator_username=creator_username,
        created_at=group.created_at,
        user_role=membership.role,
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
    # Verify group exists
    group_result = await db.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    # Check if already a member
    membership = await _get_membership(db, current_user.id, group_id)
    if membership is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already a member of this group",
        )

    # Check for existing pending request
    existing_request = await db.execute(
        select(JoinRequest).where(
            and_(
                JoinRequest.user_id == current_user.id,
                JoinRequest.group_id == group_id,
                JoinRequest.status == "PENDING",
            )
        )
    )
    if existing_request.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending request for this group",
        )

    # Create join request
    join_request = JoinRequest(
        user_id=current_user.id,
        group_id=group_id,
        status="PENDING",
    )
    db.add(join_request)
    await db.commit()
    await db.refresh(join_request)

    return JoinRequestResponse(
        id=join_request.id,
        user_id=current_user.id,
        username=current_user.username,
        group_id=group_id,
        group_name=group.name,
        status=join_request.status,
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
    # Verify admin membership
    membership = await _get_membership(db, current_user.id, group_id)
    if membership is None or membership.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group admin can view join requests",
        )

    # Fetch pending requests with user info
    requests_result = await db.execute(
        select(JoinRequest, User.username, Group.name)
        .join(User, JoinRequest.user_id == User.id)
        .join(Group, JoinRequest.group_id == Group.id)
        .where(
            and_(
                JoinRequest.group_id == group_id,
                JoinRequest.status == "PENDING",
            )
        )
    )

    items = []
    for join_req, username, group_name in requests_result.all():
        items.append(
            JoinRequestResponse(
                id=join_req.id,
                user_id=join_req.user_id,
                username=username,
                group_id=join_req.group_id,
                group_name=group_name,
                status=join_req.status,
                created_at=join_req.created_at,
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
    # Verify admin membership
    membership = await _get_membership(db, current_user.id, group_id)
    if membership is None or membership.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group admin can approve requests",
        )

    # Fetch the join request
    req_result = await db.execute(
        select(JoinRequest).where(
            and_(JoinRequest.id == request_id, JoinRequest.group_id == group_id)
        )
    )
    join_request = req_result.scalar_one_or_none()

    if join_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")

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
    await db.refresh(join_request)

    # Fetch username for response
    user_result = await db.execute(select(User.username).where(User.id == join_request.user_id))
    username = user_result.scalar_one()

    group_result = await db.execute(select(Group.name).where(Group.id == group_id))
    group_name = group_result.scalar_one()

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
    # Verify admin membership
    membership = await _get_membership(db, current_user.id, group_id)
    if membership is None or membership.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group admin can reject requests",
        )

    # Fetch the join request
    req_result = await db.execute(
        select(JoinRequest).where(
            and_(JoinRequest.id == request_id, JoinRequest.group_id == group_id)
        )
    )
    join_request = req_result.scalar_one_or_none()

    if join_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")

    if join_request.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request has already been {join_request.status.lower()}",
        )

    # Update request status only — no membership created
    join_request.status = "REJECTED"
    await db.commit()
    await db.refresh(join_request)

    # Fetch username for response
    user_result = await db.execute(select(User.username).where(User.id == join_request.user_id))
    username = user_result.scalar_one()

    group_result = await db.execute(select(Group.name).where(Group.id == group_id))
    group_name = group_result.scalar_one()

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
    # Verify membership
    membership = await _get_membership(db, current_user.id, group_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Fetch members with usernames
    members_result = await db.execute(
        select(GroupMember, User.username)
        .join(User, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
    )

    items = []
    for member, username in members_result.all():
        items.append(
            GroupMemberResponse(
                user_id=member.user_id,
                username=username,
                role=member.role,
                joined_at=member.joined_at,
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
    # Verify membership
    membership = await _get_membership(db, current_user.id, group_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # If user is an ADMIN, check that there is at least one other admin
    if membership.role == "ADMIN":
        admin_count_result = await db.execute(
            select(GroupMember).where(
                and_(
                    GroupMember.group_id == group_id,
                    GroupMember.role == "ADMIN",
                )
            )
        )
        admin_count = len(admin_count_result.all())

        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You are the only admin. Transfer admin role or delete the group before leaving.",
            )

    await db.delete(membership)
    await db.commit()

    return {"detail": "You have left the group"}
