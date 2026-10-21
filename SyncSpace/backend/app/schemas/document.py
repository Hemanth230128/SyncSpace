from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: int
    group_id: int
    uploaded_by: int
    filename: str
    file_size_bytes: int
    status: str
    error_message: Optional[str] = None
    chunk_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentChunkResponse(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    content: str
    chunk_metadata: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class SimilaritySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Search query text")
    limit: int = Field(5, ge=1, le=20, description="Maximum number of relevant chunks to return")


class SimilaritySearchResult(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    content: str
    similarity_score: float
    metadata: dict[str, Any]


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="Question about uploaded documents")
    already_sent_in_chat: bool = Field(False, description="Set to true if user question was already sent over websocket")


class SourceCitation(BaseModel):
    document_id: int
    filename: str
    chunk_id: int
    chunk_index: int
    excerpt: str
    pages: list[int] = Field(default_factory=list)
    similarity_score: float


class QuestionResponse(BaseModel):
    answer: str
    sources: list[SourceCitation] = Field(default_factory=list)

