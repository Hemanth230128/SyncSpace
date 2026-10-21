import os
import uuid
from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Document, DocumentChunk, Group, GroupMember, User
from app.schemas import (
    DocumentResponse,
    SimilaritySearchRequest,
    SimilaritySearchResult,
)
from app.services.embedding_service import (
    EmbeddingServiceError,
    generate_embeddings,
    generate_single_embedding,
)
from app.services.pdf_service import (
    PDFProcessingError,
    extract_text_and_chunks,
    validate_pdf_bytes,
)

router = APIRouter(prefix="/api/groups/{group_id}/documents", tags=["Documents"])


async def _check_group_access(
    db: AsyncSession,
    user_id: int,
    group_id: int,
    require_admin: bool = False,
) -> str:
    """
    Verifies that the group exists and that the user is an active member or admin.
    Returns the user's role ('ADMIN' or 'MEMBER').
    """
    role = await db.scalar(
        select(GroupMember.role).where(
            and_(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        )
    )

    if role is None:
        group_exists = await db.scalar(select(Group.id).where(Group.id == group_id))
        if not group_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not an authorized member of this group",
        )

    if require_admin and role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only group administrators can manage knowledge base documents",
        )

    return role


# ---------------------------------------------------------------------------
# 1. POST /api/groups/{group_id}/documents — Upload and Process PDF
# ---------------------------------------------------------------------------
@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    group_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Uploads a PDF document to the group's knowledge base, extracts text,
    generates vector embeddings, and stores chunks in PostgreSQL using pgvector.
    Admin only.
    """
    await _check_group_access(db, current_user.id, group_id, require_admin=True)

    # 1. Read file bytes and validate
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    try:
        validate_pdf_bytes(file_bytes, max_size_mb=settings.MAX_FILE_SIZE_MB)
    except PDFProcessingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # 2. Secure storage filename (UUID without exposing client paths)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    safe_filename = os.path.basename(file.filename or "document.pdf")
    storage_name = f"{uuid.uuid4().hex}.pdf"
    storage_path = os.path.join(settings.UPLOAD_DIR, storage_name)

    with open(storage_path, "wb") as f:
        f.write(file_bytes)

    # 3. Create initial document record with PROCESSING status
    doc = Document(
        group_id=group_id,
        uploaded_by=current_user.id,
        filename=safe_filename,
        storage_path=storage_path,
        file_size_bytes=len(file_bytes),
        status="PROCESSING",
        error_message=None,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # 4. Execute extraction, chunking, and embedding generation
    try:
        chunks_data = extract_text_and_chunks(
            file_bytes,
            target_chunk_tokens=settings.CHUNK_SIZE_TOKENS,
            overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
        )

        # Batch embed chunk texts
        chunk_texts = [c["content"] for c in chunks_data]
        embeddings = await generate_embeddings(chunk_texts)

        # Atomic insertion of chunks with pgvector embeddings
        chunk_models = [
            DocumentChunk(
                document_id=doc.id,
                chunk_index=c["chunk_index"],
                content=c["content"],
                embedding=embeddings[i],
                chunk_metadata=c["metadata"],
            )
            for i, c in enumerate(chunks_data)
        ]
        db.add_all(chunk_models)

        doc.status = "READY"
        doc.error_message = None
        await db.commit()
        await db.refresh(doc)

        chunk_count = len(chunk_models)

    except (PDFProcessingError, EmbeddingServiceError) as exc:
        # Gracefully record processing failure without crashing or marking READY
        doc.status = "FAILED"
        doc.error_message = str(exc)
        await db.commit()
        await db.refresh(doc)
        chunk_count = 0
    except Exception as exc:
        doc.status = "FAILED"
        doc.error_message = f"Unexpected processing error: {str(exc)}"
        await db.commit()
        await db.refresh(doc)
        chunk_count = 0

    return DocumentResponse(
        id=doc.id,
        group_id=doc.group_id,
        uploaded_by=doc.uploaded_by,
        filename=doc.filename,
        file_size_bytes=doc.file_size_bytes,
        status=doc.status,
        error_message=doc.error_message,
        chunk_count=chunk_count,
        created_at=doc.created_at,
    )


# ---------------------------------------------------------------------------
# 2. GET /api/groups/{group_id}/documents — List Group Documents
# ---------------------------------------------------------------------------
@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all documents belonging to a group, including their status and chunk counts.
    Accessible to all active group members and admins.
    """
    await _check_group_access(db, current_user.id, group_id, require_admin=False)

    stmt = (
        select(
            Document,
            func.count(DocumentChunk.id).label("chunk_count"),
        )
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(Document.group_id == group_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(stmt)

    return [
        DocumentResponse(
            id=doc.id,
            group_id=doc.group_id,
            uploaded_by=doc.uploaded_by,
            filename=doc.filename,
            file_size_bytes=doc.file_size_bytes,
            status=doc.status,
            error_message=doc.error_message,
            chunk_count=count or 0,
            created_at=doc.created_at,
        )
        for doc, count in result.all()
    ]


# ---------------------------------------------------------------------------
# 3. GET /api/groups/{group_id}/documents/{document_id} — Document Details
# ---------------------------------------------------------------------------
@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    group_id: int,
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves safe metadata and current processing status for a specific document.
    """
    await _check_group_access(db, current_user.id, group_id, require_admin=False)

    stmt = (
        select(
            Document,
            func.count(DocumentChunk.id).label("chunk_count"),
        )
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(and_(Document.id == document_id, Document.group_id == group_id))
        .group_by(Document.id)
    )
    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    doc, count = row
    return DocumentResponse(
        id=doc.id,
        group_id=doc.group_id,
        uploaded_by=doc.uploaded_by,
        filename=doc.filename,
        file_size_bytes=doc.file_size_bytes,
        status=doc.status,
        error_message=doc.error_message,
        chunk_count=count or 0,
        created_at=doc.created_at,
    )


# ---------------------------------------------------------------------------
# 4. DELETE /api/groups/{group_id}/documents/{document_id} — Delete Document
# ---------------------------------------------------------------------------
@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    group_id: int,
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes a document and cascades deletion of all associated chunks and vector embeddings.
    Admin only.
    """
    await _check_group_access(db, current_user.id, group_id, require_admin=True)

    doc = await db.scalar(
        select(Document).where(
            and_(Document.id == document_id, Document.group_id == group_id)
        )
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Safely remove underlying physical file if it exists
    if doc.storage_path and os.path.exists(doc.storage_path):
        try:
            os.remove(doc.storage_path)
        except OSError:
            pass

    # Database cascade safely deletes associated chunks and embeddings
    await db.delete(doc)
    await db.commit()

    return {"detail": f"Document '{doc.filename}' and its vector chunks deleted successfully"}


# ---------------------------------------------------------------------------
# 5. POST /api/groups/{group_id}/documents/search — Internal Similarity Search
# ---------------------------------------------------------------------------
@router.post("/search", response_model=list[SimilaritySearchResult])
async def search_documents(
    group_id: int,
    req: SimilaritySearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Minimal internal similarity search endpoint to verify stored embeddings in pgvector.
    Strictly isolated to documents belonging to group_id.
    """
    await _check_group_access(db, current_user.id, group_id, require_admin=False)

    try:
        query_vector = await generate_single_embedding(req.query)
    except EmbeddingServiceError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    # Cosine distance via pgvector: 0.0 means identical, 2.0 means opposite
    # Cosine similarity = 1.0 - cosine_distance
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
        .limit(req.limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        SimilaritySearchResult(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            filename=r.filename,
            chunk_index=r.chunk_index,
            content=r.content,
            similarity_score=round(max(0.0, 1.0 - float(r.distance)), 4),
            metadata=r.chunk_metadata,
        )
        for r in rows
    ]
