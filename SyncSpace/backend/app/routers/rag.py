import json
import logging
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.connection_manager import manager
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Document, DocumentChunk, Group, Message, User
from app.routers.documents import _check_group_access
from app.schemas import QuestionRequest, QuestionResponse, SourceCitation
from app.services.embedding_service import (
    EmbeddingServiceError,
    generate_single_embedding,
)
from app.services.rag_service import RAGServiceError, generate_grounded_answer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["RAG Question Answering"])


async def _handle_ask_question(
    group_id: int,
    req: QuestionRequest,
    current_user: User,
    db: AsyncSession,
) -> QuestionResponse:
    """
    Core RAG question answering logic:
    1. Validate question input
    2. Enforce group membership authorization
    3. Generate question embedding
    4. Retrieve pgvector cosine similarity matches scoped strictly to group READY docs
    5. Build grounded, injection-resistant prompt and generate LLM answer
    6. Return grounded answer with verifiable source citations
    """
    # 1. Validate question length and content
    question_clean = req.question.strip()
    if not question_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty or whitespace.",
        )
    if len(question_clean) > settings.MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Question exceeds maximum length of {settings.MAX_QUESTION_LENGTH} characters.",
        )

    # 2. Authorization check & group context retrieval
    await _check_group_access(db, current_user.id, group_id, require_admin=False)
    group = await db.scalar(select(Group).where(Group.id == group_id))
    group_topic = (
        group.description.strip()
        if (group and group.description and group.description.strip())
        else (group.name if group else "this group")
    )

    # 3. Generate embedding for user's question
    try:
        query_vector = await generate_single_embedding(question_clean)
    except EmbeddingServiceError as exc:
        logger.error(f"Embedding generation error for question: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate question embedding: {str(exc)}",
        )

    # 4. Vector retrieval filtered strictly to this group and READY documents
    distance_expr = DocumentChunk.embedding.cosine_distance(query_vector)

    stmt = (
        select(
            DocumentChunk.id.label("chunk_id"),
            Document.id.label("document_id"),
            Document.filename,
            DocumentChunk.chunk_index,
            DocumentChunk.content,
            distance_expr.label("distance"),
            DocumentChunk.chunk_metadata,
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            and_(
                Document.group_id == group_id,
                Document.status == "READY",
            )
        )
        .order_by(distance_expr.asc())
        .limit(settings.RAG_TOP_K)
    )

    result = await db.execute(stmt)
    rows = result.all()

    retrieved_chunks: list[dict[str, Any]] = []
    sources: list[SourceCitation] = []

    # 5. Handle case where no relevant chunks exist in this group
    if not rows:
        answer = (
            f"This chat is for {group_topic}. "
            "Anything else is not in the uploaded documents and cannot be solved here. "
            f"Please ask questions related to {group_topic}!"
        )
    else:
        # 6. Prepare context and build verifiable citations
        for r in rows:
            metadata = r.chunk_metadata or {}
            pages = metadata.get("pages", [])
            # Cosine distance range: 0.0 (identical) to 2.0 (opposite). Score in [0.0, 1.0]
            similarity_score = round(max(0.0, 1.0 - float(r.distance)), 4)

            retrieved_chunks.append({
                "chunk_id": r.chunk_id,
                "filename": r.filename,
                "pages": pages,
                "content": r.content,
            })

            # Excerpt for citation card
            excerpt = r.content.strip()
            if len(excerpt) > 240:
                excerpt = excerpt[:237] + "..."

            sources.append(
                SourceCitation(
                    document_id=r.document_id,
                    filename=r.filename,
                    chunk_id=r.chunk_id,
                    chunk_index=r.chunk_index,
                    excerpt=excerpt,
                    pages=pages,
                    similarity_score=similarity_score,
                )
            )

        # 7. Generate grounded answer via LLM
        try:
            answer = await generate_grounded_answer(
                question=question_clean,
                retrieved_chunks=retrieved_chunks,
                group_topic=group_topic,
            )
        except RAGServiceError as exc:
            logger.error(f"RAG LLM generation error: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI generation failed: {str(exc)}",
            )

    # 8. Collaborative Chat Sharing: Persist & Broadcast to all group members
    try:
        now_utc = datetime.now(timezone.utc)

        # 8a. Find or create AI Bot User
        ai_user = await db.scalar(select(User).where(User.username == "SyncSpace AI"))
        if not ai_user:
            ai_user = User(username="SyncSpace AI", password_hash="SYSTEM_BOT_NO_LOGIN")
            db.add(ai_user)
            await db.flush()

        # 8b. Persist user's question message in group history (if not already sent via websocket)
        if not req.already_sent_in_chat:
            user_msg = Message(
                group_id=group_id,
                user_id=current_user.id,
                content=f"🤖 @AI: {question_clean}",
                created_at=now_utc,
            )
            db.add(user_msg)
            await db.flush()

            await manager.broadcast(
                group_id,
                {
                    "id": user_msg.id,
                    "group_id": group_id,
                    "user_id": current_user.id,
                    "username": current_user.username,
                    "content": f"🤖 @AI: {question_clean}",
                    "created_at": now_utc.isoformat(),
                },
            )

        # 8c. Persist AI response message with embedded sources
        sources_meta = [s.model_dump() for s in sources]
        sources_tag = f"\n\n<!--sources:{json.dumps(sources_meta)}-->" if sources_meta else ""
        ai_msg = Message(
            group_id=group_id,
            user_id=ai_user.id,
            content=f"{answer}{sources_tag}",
            created_at=now_utc,
        )
        db.add(ai_msg)
        await db.commit()
        await manager.broadcast(
            group_id,
            {
                "id": ai_msg.id,
                "group_id": group_id,
                "user_id": ai_user.id,
                "username": "SyncSpace AI",
                "is_ai": True,
                "content": answer,
                "sources": sources_meta,
                "created_at": now_utc.isoformat(),
            },
        )
    except Exception as exc:
        logger.warning(f"Could not broadcast AI Q&A to group chat: {exc}")

    return QuestionResponse(
        answer=answer,
        sources=sources,
    )


@router.post("/api/groups/{group_id}/ask", response_model=QuestionResponse)
async def ask_group_api(
    group_id: int,
    req: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    RAG question answering endpoint (Frontend /api prefix convention).
    Ask a natural-language question against the group's uploaded PDF knowledge base.
    """
    return await _handle_ask_question(group_id, req, current_user, db)


@router.post("/groups/{group_id}/ask", response_model=QuestionResponse)
async def ask_group_direct(
    group_id: int,
    req: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    RAG question answering endpoint (Direct /groups prefix specification).
    Ask a natural-language question against the group's uploaded PDF knowledge base.
    """
    return await _handle_ask_question(group_id, req, current_user, db)
