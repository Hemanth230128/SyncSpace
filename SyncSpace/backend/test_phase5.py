import asyncio
import io
import json
import sys
import urllib.request
import urllib.error

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings
from app.database import async_session_maker
from app.models import Document, DocumentChunk, Group, GroupMember, User
from app.security import create_access_token
from sqlalchemy import select

BASE_URL = "http://127.0.0.1:8000"


def make_text_pdf(text: str) -> bytes:
    """Generates a valid minimal PDF with text content."""
    content = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET"
    stream_len = len(content)
    pdf = f"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length {stream_len} >> stream
{content}
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000300 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
370
%%EOF"""
    return pdf.encode("latin1")


def post_multipart(url: str, token: str, filename: str, file_bytes: bytes):
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode("latin1") + file_bytes + f"\r\n--{boundary}--\r\n".encode("latin1")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    return req


async def run_tests():
    print("=" * 60)
    print("🚀 Running Phase 5: PDF Knowledge Base & pgvector Test Suite")
    print("=" * 60)

    # 1. Setup test tokens & group
    async with async_session_maker() as db:
        # Find an admin and a member of group 1
        members = (
            await db.execute(
                select(GroupMember.user_id, GroupMember.role, User.username)
                .join(User, GroupMember.user_id == User.id)
                .where(GroupMember.group_id == 1)
            )
        ).all()

        admin = next((m for m in members if m.role == "ADMIN"), None)
        member = next((m for m in members if m.role == "MEMBER"), None)

    if not admin:
        print("❌ Could not find an admin for group 1")
        return

    admin_token = create_access_token({"sub": str(admin.user_id), "username": admin.username})
    member_token = (
        create_access_token({"sub": str(member.user_id), "username": member.username})
        if member
        else None
    )
    non_member_token = create_access_token({"sub": "9999", "username": "intruder"})

    print(f"👤 Testing with Admin: #{admin.user_id} ({admin.username})")
    if member:
        print(f"👤 Testing with Member: #{member.user_id} ({member.username})")

    # ------------------------------------------------------------------
    # Test 1: Upload a valid text PDF as Admin
    # ------------------------------------------------------------------
    print("\n--- Test 1: Admin uploads valid PDF document ---")
    pdf_text = "SyncSpace is an AI Collaborative Chat Platform providing real-time team communication and PDF knowledge base search using pgvector."
    pdf_data = make_text_pdf(pdf_text)

    # Temporarily allow mock fallback if no API key is yet configured
    original_key = settings.GEMINI_API_KEY
    if not settings.effective_gemini_api_key:
        settings.GEMINI_API_KEY = "MOCK"

    req = post_multipart(f"{BASE_URL}/api/groups/1/documents", admin_token, "test_handbook.pdf", pdf_data)
    try:
        with urllib.request.urlopen(req) as resp:
            doc_data = json.loads(resp.read())
            print(f"✅ Document uploaded successfully: ID={doc_data['id']}, status={doc_data['status']}, chunks={doc_data['chunk_count']}")
            uploaded_doc_id = doc_data["id"]
    except urllib.error.HTTPError as e:
        print(f"❌ Upload failed with code {e.code}: {e.read().decode()}")
        return

    # ------------------------------------------------------------------
    # Test 2: Verify chunks and vector dimensions in PostgreSQL
    # ------------------------------------------------------------------
    print("\n--- Test 2: Verify pgvector chunks and 768 dimensions in DB ---")
    async with async_session_maker() as db:
        chunks = (
            await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == uploaded_doc_id)
            )
        ).scalars().all()

        print(f"✅ Found {len(chunks)} chunks in PostgreSQL for document {uploaded_doc_id}")
        assert len(chunks) > 0, "No chunks found in database!"
        first_chunk = chunks[0]
        # Verify vector dimension
        embedding_list = list(first_chunk.embedding)
        print(f"✅ Chunk index {first_chunk.chunk_index} has embedding length: {len(embedding_list)} (expected 768)")
        assert len(embedding_list) == 768, f"Expected 768 dimensions, got {len(embedding_list)}"

    # ------------------------------------------------------------------
    # Test 3: Test pgvector similarity search
    # ------------------------------------------------------------------
    print("\n--- Test 3: Test pgvector similarity search ---")
    search_payload = json.dumps({"query": "What is SyncSpace platform?", "limit": 3}).encode()
    search_req = urllib.request.Request(
        f"{BASE_URL}/api/groups/1/documents/search",
        data=search_payload,
        headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(search_req) as resp:
        results = json.loads(resp.read())
        print(f"✅ Search returned {len(results)} relevant chunks:")
        for r in results:
            print(f"   • Chunk #{r['chunk_id']} from '{r['filename']}' - similarity score: {r['similarity_score']}")
            print(f"     Content snippet: {r['content'][:70]}...")

    # ------------------------------------------------------------------
    # Test 4: Ordinary member cannot upload a document (403 Forbidden)
    # ------------------------------------------------------------------
    if member_token:
        print("\n--- Test 4: Ordinary member cannot upload (403 check) ---")
        mem_req = post_multipart(f"{BASE_URL}/api/groups/1/documents", member_token, "member_attempt.pdf", pdf_data)
        try:
            with urllib.request.urlopen(mem_req) as resp:
                print("❌ Member was unexpectedly allowed to upload!")
        except urllib.error.HTTPError as e:
            print(f"✅ Correctly rejected with HTTP {e.code}: {e.read().decode()}")
            assert e.code == 403, f"Expected 403, got {e.code}"

    # ------------------------------------------------------------------
    # Test 5: Non-member cannot access group documents (403/404 check)
    # ------------------------------------------------------------------
    print("\n--- Test 5: Non-member cannot access documents ---")
    non_req = urllib.request.Request(
        f"{BASE_URL}/api/groups/1/documents",
        headers={"Authorization": f"Bearer {non_member_token}"},
    )
    try:
        with urllib.request.urlopen(non_req) as resp:
            print("❌ Non-member was unexpectedly allowed access!")
    except urllib.error.HTTPError as e:
        print(f"✅ Correctly rejected with HTTP {e.code}")

    # ------------------------------------------------------------------
    # Test 6: Malformed PDF fails gracefully
    # ------------------------------------------------------------------
    print("\n--- Test 6: Malformed PDF fails gracefully (400 check) ---")
    malformed_req = post_multipart(f"{BASE_URL}/api/groups/1/documents", admin_token, "corrupted.pdf", b"This is not a pdf file")
    try:
        with urllib.request.urlopen(malformed_req) as resp:
            print("❌ Corrupted file was unexpectedly accepted!")
    except urllib.error.HTTPError as e:
        print(f"✅ Correctly rejected with HTTP {e.code}: {e.read().decode()}")
        assert e.code == 400, f"Expected 400, got {e.code}"

    # ------------------------------------------------------------------
    # Test 7: Delete document cascades and removes chunks from PostgreSQL
    # ------------------------------------------------------------------
    print("\n--- Test 7: Delete document removes chunks from PostgreSQL ---")
    del_req = urllib.request.Request(
        f"{BASE_URL}/api/groups/1/documents/{uploaded_doc_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        method="DELETE",
    )
    with urllib.request.urlopen(del_req) as resp:
        del_data = json.loads(resp.read())
        print(f"✅ Delete response: {del_data['detail']}")

    # Verify chunks are gone from PostgreSQL
    async with async_session_maker() as db:
        remaining_chunks = (
            await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == uploaded_doc_id)
            )
        ).scalars().all()
        print(f"✅ Remaining chunks in DB for deleted document: {len(remaining_chunks)} (expected 0)")
        assert len(remaining_chunks) == 0, "Chunks were not deleted!"

    # Restore settings
    settings.GEMINI_API_KEY = original_key

    print("\n" + "=" * 60)
    print("🎉 All Phase 5 manual tests passed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
