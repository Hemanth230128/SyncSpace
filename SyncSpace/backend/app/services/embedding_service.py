import hashlib
import math
from typing import Optional
import httpx

from app.config import settings

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class EmbeddingServiceError(Exception):
    """Custom exception raised when vector embedding generation fails."""
    pass


def _create_mock_embedding(text: str, dim: int = 768) -> list[float]:
    """
    Generates a deterministic, unit-normalized 768-dimensional vector
    based on MD5 hash of text for local testing when no API key is available.
    """
    seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
    raw = [math.sin(seed + i) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generates 768-dimensional vector embeddings for a list of text strings
    using Google Gemini's embedding model via batched HTTP requests.
    """
    if not texts:
        return []

    api_key = settings.effective_gemini_api_key.strip()

    # If no API key configured or explicitly MOCK, check behavior
    if not api_key:
        raise EmbeddingServiceError(
            "Google Gemini API key not configured. Add GEMINI_API_KEY to backend/.env (get a free key at https://aistudio.google.com)."
        )

    if api_key.upper() == "MOCK":
        return [_create_mock_embedding(t, settings.EMBEDDING_DIMENSION) for t in texts]

    # Batch in groups of 50 to stay well within Gemini API request payload limits
    batch_size = 50
    all_embeddings: list[list[float]] = []
    embed_url = f"{GEMINI_BASE_URL}/{settings.EMBEDDING_MODEL}:batchEmbedContents"

    async with httpx.AsyncClient(timeout=45.0) as client:
        for i in range(0, len(texts), batch_size):
            batch_slice = texts[i : i + batch_size]
            payload = {
                "requests": [
                    {
                        "model": settings.EMBEDDING_MODEL,
                        "content": {"parts": [{"text": t[:8000]}]},
                        "outputDimensionality": settings.EMBEDDING_DIMENSION,
                    }
                    for t in batch_slice
                ]
            }

            try:
                response = await client.post(
                    f"{embed_url}?key={api_key}",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            except httpx.TimeoutException as exc:
                raise EmbeddingServiceError(
                    "Timeout while connecting to Google Gemini embedding service."
                ) from exc
            except Exception as exc:
                raise EmbeddingServiceError(
                    f"Failed to communicate with Google Gemini API: {str(exc)}"
                ) from exc

            if response.status_code != 200:
                err_detail = response.text
                try:
                    err_json = response.json()
                    err_detail = err_json.get("error", {}).get("message", err_detail)
                except Exception:
                    pass
                raise EmbeddingServiceError(
                    f"Google Gemini Embedding API error ({response.status_code}): {err_detail}"
                )

            data = response.json()
            embeddings_data = data.get("embeddings", [])
            if len(embeddings_data) != len(batch_slice):
                raise EmbeddingServiceError(
                    f"Expected {len(batch_slice)} embeddings from Gemini API, but received {len(embeddings_data)}."
                )

            for item in embeddings_data:
                vec = item.get("values", [])
                if len(vec) != settings.EMBEDDING_DIMENSION:
                    raise EmbeddingServiceError(
                        f"Expected {settings.EMBEDDING_DIMENSION}-dim embedding, but received {len(vec)} dimensions."
                    )
                all_embeddings.append(vec)

    return all_embeddings


async def generate_single_embedding(text: str) -> list[float]:
    """
    Generates a 768-dimensional vector embedding for a single text query string.
    """
    results = await generate_embeddings([text])
    if not results:
        raise EmbeddingServiceError("Failed to generate embedding for query.")
    return results[0]
