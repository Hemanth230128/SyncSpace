import io
import re
from typing import Any
from pypdf import PdfReader


class PDFProcessingError(Exception):
    """Custom exception raised when PDF validation, extraction, or chunking fails."""
    pass


def validate_pdf_bytes(file_bytes: bytes, max_size_mb: int = 15) -> None:
    """
    Validates that file bytes start with the %PDF- magic signature
    and do not exceed the configured maximum size.
    """
    if len(file_bytes) > max_size_mb * 1024 * 1024:
        raise PDFProcessingError(f"File size exceeds maximum allowed limit of {max_size_mb} MB.")

    if not file_bytes.startswith(b"%PDF-"):
        raise PDFProcessingError("Uploaded file is not a valid PDF document (missing %PDF- signature).")


def extract_text_and_chunks(
    file_bytes: bytes,
    target_chunk_tokens: int = 600,
    overlap_tokens: int = 100,
) -> list[dict[str, Any]]:
    """
    Extracts text from each page using pypdf and splits into semantically coherent
    chunks with overlapping context windows and page metadata.

    Approximate rule of thumb: 1 token ≈ 4 characters in English.
    target_chunk_tokens (600 tokens) ≈ 2400 chars.
    overlap_tokens (100 tokens) ≈ 400 chars.
    """
    validate_pdf_bytes(file_bytes)

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        raise PDFProcessingError(f"Malformed or corrupted PDF document: {str(exc)}") from exc

    if len(reader.pages) == 0:
        raise PDFProcessingError("PDF document has 0 pages.")

    # 1. Extract text page by page with page numbering
    pages_text: list[tuple[int, str]] = []
    total_extracted_chars = 0

    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""

        # Normalize redundant spaces and newlines
        cleaned = re.sub(r"\s+", " ", page_text).strip()
        if cleaned:
            pages_text.append((page_num, cleaned))
            total_extracted_chars += len(cleaned)

    # 2. Check for textless / scanned documents
    if total_extracted_chars < 30:
        raise PDFProcessingError(
            "PDF contains no extractable text. Scanned or image-only PDFs without embedded text layers (OCR) are not supported."
        )

    # 3. Create overlapping chunks across document pages
    chunk_char_target = target_chunk_tokens * 4
    overlap_char_target = overlap_tokens * 4
    step_size = max(chunk_char_target - overlap_char_target, 200)

    # Combine text with page boundary markers
    full_text_segments: list[tuple[int, str]] = []
    for page_num, text in pages_text:
        # Split page into word tokens
        words = text.split(" ")
        for w in words:
            if w:
                full_text_segments.append((page_num, w))

    # Build chunks by words
    chunks: list[dict[str, Any]] = []
    total_words = len(full_text_segments)
    
    # Approx 1 token ≈ 0.75 words -> 600 tokens ≈ 450 words, 100 overlap ≈ 75 words
    target_words_per_chunk = int(target_chunk_tokens * 0.75)
    overlap_words = int(overlap_tokens * 0.75)
    word_step = max(target_words_per_chunk - overlap_words, 50)

    start_idx = 0
    chunk_counter = 0

    while start_idx < total_words:
        end_idx = min(start_idx + target_words_per_chunk, total_words)
        chunk_segment = full_text_segments[start_idx:end_idx]

        if not chunk_segment:
            break

        chunk_words = [item[1] for item in chunk_segment]
        chunk_text = " ".join(chunk_words).strip()

        # Identify pages represented in this chunk
        pages_in_chunk = sorted(list(set(item[0] for item in chunk_segment)))

        if len(chunk_text) >= 20:
            chunks.append({
                "chunk_index": chunk_counter,
                "content": chunk_text,
                "metadata": {
                    "pages": pages_in_chunk,
                    "word_count": len(chunk_words),
                    "char_count": len(chunk_text),
                    "estimated_tokens": int(len(chunk_words) / 0.75),
                },
            })
            chunk_counter += 1

        if end_idx >= total_words:
            break

        start_idx += word_step

    if not chunks:
        raise PDFProcessingError("Could not generate valid text chunks from PDF content.")

    return chunks
