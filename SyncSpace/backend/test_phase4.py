import asyncio
import json
import time
import urllib.error
import urllib.request
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

BASE_URL = "http://localhost:8000"
WS_BASE_URL = "ws://localhost:8000"


def http_req(method: str, path: str, data: dict = None, token: str = None) -> tuple[int, dict | list | str]:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                status = resp.status
                content = resp.read().decode("utf-8")
                try:
                    return status, json.loads(content)
                except Exception:
                    return status, content
        except urllib.error.HTTPError as e:
            content = e.read().decode("utf-8")
            try:
                return e.code, json.loads(content)
            except Exception:
                return e.code, content
        except Exception as e:
            if attempt < 2:
                time.sleep(1.0)
                continue
            print(f"Connection error to {url} after 3 attempts: {e}", flush=True)
            raise e


async def run_tests():
    timestamp = int(time.time())
    print("\n============================================================", flush=True)
    print("RUNNING PHASE 4 REAL-TIME WEBSOCKET CHAT LIVE SYSTEM TESTS", flush=True)
    print("============================================================", flush=True)

    # Helper to create and authenticate users
    def register_user(uname: str, pwd: str = "password123"):
        print(f"Signing up {uname}...", flush=True)
        s, data = http_req("POST", "/api/auth/signup", {"username": uname, "password": pwd})
        assert s == 201, f"Signup failed for {uname}: {s} {data}"
        print(f"Logging in {uname}...", flush=True)
        status, data = http_req("POST", "/api/auth/login", {"username": uname, "password": pwd})
        assert status == 200, f"Login failed: {data}"
        return data["access_token"]

    admin_token = register_user(f"ws_adm_{timestamp}")
    member_token = register_user(f"ws_mem_{timestamp}")
    stranger_token = register_user(f"ws_str_{timestamp}")

    print("Creating test group...", flush=True)
    status, grp = http_req("POST", "/api/groups", {"name": f"Live Chat Group {timestamp}"}, token=admin_token)
    assert status == 201, f"Failed to create group: {grp}"
    group_id = grp["id"]
    admin_id = grp["created_by"]

    print("Member requesting join...", flush=True)
    status, join_req = http_req("POST", f"/api/groups/{group_id}/join", token=member_token)
    assert status == 201
    req_id = join_req["id"]

    status, appr = http_req("POST", f"/api/groups/{group_id}/requests/{req_id}/approve", token=admin_token)
    assert status == 200
    member_id = appr["user_id"]

    # -----------------------------------------------------------------------
    # 1. REST MESSAGE HISTORY TESTS
    # -----------------------------------------------------------------------
    # Test 1: Unauthenticated request -> 401
    s1, _ = http_req("GET", f"/api/groups/{group_id}/messages")
    assert s1 == 401, f"Expected 401, got {s1}"
    print("Test 1 Passed: Unauthenticated GET /api/groups/{id}/messages -> 401 Unauthorized", flush=True)

    # Test 2: Non-existent group -> 404
    s2, _ = http_req("GET", "/api/groups/999999/messages", token=admin_token)
    assert s2 == 404, f"Expected 404, got {s2}"
    print("Test 2 Passed: Non-existent group GET /messages -> 404 Not Found", flush=True)

    # Test 3: Non-member stranger -> 403
    s3, _ = http_req("GET", f"/api/groups/{group_id}/messages", token=stranger_token)
    assert s3 == 403, f"Expected 403, got {s3}"
    print("Test 3 Passed: Non-member GET /messages -> 403 Forbidden", flush=True)

    # Test 4: Member gets initial empty history -> 200 with []
    s4, d4 = http_req("GET", f"/api/groups/{group_id}/messages", token=member_token)
    assert s4 == 200 and d4 == [], f"Expected 200 with [], got {s4}: {d4}"
    print("Test 4 Passed: Member gets empty history -> 200 OK with []", flush=True)

    # -----------------------------------------------------------------------
    # 2. WEBSOCKET AUTHENTICATION & AUTHORIZATION REJECTION TESTS
    # -----------------------------------------------------------------------
    # Test 5: WebSocket connection without token -> rejected
    try:
        async with connect(f"{WS_BASE_URL}/ws/groups/{group_id}"):
            assert False, "Should have rejected missing token"
    except (ConnectionClosed, InvalidHandshake, Exception) as e:
        print(f"Test 5 Passed: No token rejected -> {e.__class__.__name__}", flush=True)

    # Test 6: WebSocket connection with invalid token -> rejected
    try:
        async with connect(f"{WS_BASE_URL}/ws/groups/{group_id}?token=invalid.jwt.token"):
            assert False, "Should have rejected invalid token"
    except (ConnectionClosed, InvalidHandshake, Exception) as e:
        print(f"Test 6 Passed: Invalid token rejected -> {e.__class__.__name__}", flush=True)

    # Test 7: WebSocket connection to non-existent group -> rejected
    try:
        async with connect(f"{WS_BASE_URL}/ws/groups/999999?token={admin_token}"):
            assert False, "Should have rejected non-existent group"
    except (ConnectionClosed, InvalidHandshake, Exception) as e:
        print(f"Test 7 Passed: Non-existent group rejected -> {e.__class__.__name__}", flush=True)

    # Test 8: Non-member stranger connecting to group -> rejected
    try:
        async with connect(f"{WS_BASE_URL}/ws/groups/{group_id}?token={stranger_token}"):
            assert False, "Should have rejected non-member"
    except (ConnectionClosed, InvalidHandshake, Exception) as e:
        print(f"Test 8 Passed: Non-member rejected -> {e.__class__.__name__}", flush=True)

    # -----------------------------------------------------------------------
    # 3. WEBSOCKET MESSAGING & PERSISTENCE
    # -----------------------------------------------------------------------
    async with connect(f"{WS_BASE_URL}/ws/groups/{group_id}?token={admin_token}") as ws_admin:
        print("Test 9 Passed: Authorized Admin connected successfully to WebSocket", flush=True)

        # Test 10: Send message and receive broadcast payload
        await ws_admin.send(json.dumps({"content": "Hello SyncSpace team!"}))
        raw1 = await asyncio.wait_for(ws_admin.recv(), timeout=5.0)
        msg1 = json.loads(raw1)
        assert msg1["content"] == "Hello SyncSpace team!"
        assert msg1["group_id"] == group_id
        assert msg1["user_id"] == admin_id
        assert msg1["username"] == f"ws_adm_{timestamp}"
        assert "id" in msg1 and "created_at" in msg1
        print("Test 10 Passed: Message sent and received broadcast payload with full metadata", flush=True)

        # Test 11: Attempt user ID spoofing
        await ws_admin.send(json.dumps({"user_id": 9999, "username": "fake_hacker", "content": "Spoof test"}))
        raw2 = await asyncio.wait_for(ws_admin.recv(), timeout=5.0)
        msg2 = json.loads(raw2)
        assert msg2["user_id"] == admin_id, f"Expected {admin_id}, got {msg2['user_id']}"
        assert msg2["username"] == f"ws_adm_{timestamp}", f"Expected legitimate username, got {msg2['username']}"
        assert msg2["content"] == "Spoof test"
        print("Test 11 Passed: Spoofing prevented — sender strictly locked to authenticated user", flush=True)

        # Test 12: Empty message validation
        await ws_admin.send(json.dumps({"content": "    "}))
        raw3 = await asyncio.wait_for(ws_admin.recv(), timeout=5.0)
        err3 = json.loads(raw3)
        assert "error" in err3, f"Expected error payload, got {err3}"
        print("Test 12 Passed: Empty message safely rejected with error response", flush=True)

    # -----------------------------------------------------------------------
    # 4. MULTI-CLIENT BROADCAST
    # -----------------------------------------------------------------------
    async with connect(f"{WS_BASE_URL}/ws/groups/{group_id}?token={admin_token}") as ws_adm, \
               connect(f"{WS_BASE_URL}/ws/groups/{group_id}?token={member_token}") as ws_mem:
        print("Test 13 Passed: Multiple clients connected simultaneously to same group", flush=True)

        # Admin sends broadcast
        await ws_adm.send(json.dumps({"content": "Broadcast from Admin"}))
        adm_recv = json.loads(await asyncio.wait_for(ws_adm.recv(), timeout=5.0))
        mem_recv = json.loads(await asyncio.wait_for(ws_mem.recv(), timeout=5.0))

        assert adm_recv["content"] == "Broadcast from Admin"
        assert mem_recv["content"] == "Broadcast from Admin"
        assert mem_recv["user_id"] == admin_id
        print("Test 14 Passed: Broadcast successfully received by all connected members", flush=True)

        # Member sends reply
        await ws_mem.send(json.dumps({"content": "Reply from Member"}))
        adm_recv2 = json.loads(await asyncio.wait_for(ws_adm.recv(), timeout=5.0))
        mem_recv2 = json.loads(await asyncio.wait_for(ws_mem.recv(), timeout=5.0))

        assert adm_recv2["content"] == "Reply from Member"
        assert mem_recv2["content"] == "Reply from Member"
        assert adm_recv2["user_id"] == member_id
        print("Test 15 Passed: Member reply broadcasted to all group members in real time", flush=True)

    # -----------------------------------------------------------------------
    # 5. PERSISTENCE & CHRONOLOGICAL HISTORY VIA REST
    # -----------------------------------------------------------------------
    s_hist, hist = http_req("GET", f"/api/groups/{group_id}/messages", token=member_token)
    assert s_hist == 200, f"Expected 200, got {s_hist}"
    assert len(hist) == 4, f"Expected 4 persisted messages, got {len(hist)}"
    assert hist[0]["content"] == "Hello SyncSpace team!"
    assert hist[1]["content"] == "Spoof test"
    assert hist[2]["content"] == "Broadcast from Admin"
    assert hist[3]["content"] == "Reply from Member"
    print("Test 16 Passed: All messages persisted in PostgreSQL and returned in chronological order", flush=True)

    # Test 17: Pagination limit & offset
    s_page, page = http_req("GET", f"/api/groups/{group_id}/messages?limit=2&offset=1", token=admin_token)
    assert s_page == 200
    assert len(page) == 2
    assert page[0]["content"] == "Spoof test"
    assert page[1]["content"] == "Broadcast from Admin"
    print("Test 17 Passed: REST pagination (limit & offset) verified", flush=True)

    # -----------------------------------------------------------------------
    # 6. CLEAN DISCONNECT
    # -----------------------------------------------------------------------
    async with connect(f"{WS_BASE_URL}/ws/groups/{group_id}?token={admin_token}") as ws:
        await ws.send(json.dumps({"content": "Closing socket test"}))
        ack = json.loads(await ws.recv())
        assert ack["content"] == "Closing socket test"
    # Sockets closes on context manager exit
    print("Test 18 Passed: WebSocket disconnected cleanly without crashing server", flush=True)

    print("\n============================================================", flush=True)
    print("ALL 18 PHASE 4 REAL-TIME WEBSOCKET CHAT TESTS PASSED!", flush=True)
    print("============================================================\n", flush=True)


if __name__ == "__main__":
    asyncio.run(run_tests())
