import asyncio
import time
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database import init_db


async def benchmark():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Signup admin
        admin_auth = await ac.post("/api/auth/signup", json={"username": "bench_admin", "password": "password123"})
        if admin_auth.status_code == 409:
            login_res = await ac.post("/api/auth/login", json={"username": "bench_admin", "password": "password123"})
            admin_token = login_res.json()["access_token"]
        else:
            login_res = await ac.post("/api/auth/login", json={"username": "bench_admin", "password": "password123"})
            admin_token = login_res.json()["access_token"]

        # Signup regular member
        member_auth = await ac.post("/api/auth/signup", json={"username": "bench_user", "password": "password123"})
        if member_auth.status_code == 409:
            login_res = await ac.post("/api/auth/login", json={"username": "bench_user", "password": "password123"})
            member_token = login_res.json()["access_token"]
        else:
            login_res = await ac.post("/api/auth/login", json={"username": "bench_user", "password": "password123"})
            member_token = login_res.json()["access_token"]

        headers_admin = {"Authorization": f"Bearer {admin_token}"}
        headers_member = {"Authorization": f"Bearer {member_token}"}

        print("\n--- MEASURING BASELINE TIMES ---")

        # 1. Create Group
        t0 = time.perf_counter()
        cg_res = await ac.post("/api/groups", json={"name": f"Benchmark Group {time.time()}"}, headers=headers_admin)
        t_create = (time.perf_counter() - t0) * 1000
        group_id = cg_res.json()["id"]
        print(f"1. Create Group: {t_create:.2f} ms")

        # 2. List Groups
        t0 = time.perf_counter()
        lg_res = await ac.get("/api/groups", headers=headers_admin)
        t_list = (time.perf_counter() - t0) * 1000
        print(f"2. List Groups: {t_list:.2f} ms ({len(lg_res.json())} groups)")

        # 3. Request to Join
        t0 = time.perf_counter()
        req_res = await ac.post(f"/api/groups/{group_id}/join", headers=headers_member)
        t_join_req = (time.perf_counter() - t0) * 1000
        request_id = req_res.json()["id"]
        print(f"3. Request to Join: {t_join_req:.2f} ms")

        # 4. List Join Requests
        t0 = time.perf_counter()
        reqs_res = await ac.get(f"/api/groups/{group_id}/requests", headers=headers_admin)
        t_list_reqs = (time.perf_counter() - t0) * 1000
        print(f"4. List Join Requests: {t_list_reqs:.2f} ms")

        # 5. Approve Request
        t0 = time.perf_counter()
        app_res = await ac.post(f"/api/groups/{group_id}/requests/{request_id}/approve", headers=headers_admin)
        t_approve = (time.perf_counter() - t0) * 1000
        print(f"5. Approve Request: {t_approve:.2f} ms")

        # 6. List Members
        t0 = time.perf_counter()
        mem_res = await ac.get(f"/api/groups/{group_id}/members", headers=headers_admin)
        t_members = (time.perf_counter() - t0) * 1000
        print(f"6. List Members: {t_members:.2f} ms")

        # 7. Leave Group
        t0 = time.perf_counter()
        leave_res = await ac.delete(f"/api/groups/{group_id}/leave", headers=headers_member)
        t_leave = (time.perf_counter() - t0) * 1000
        print(f"7. Leave Group: {t_leave:.2f} ms")


if __name__ == "__main__":
    asyncio.run(benchmark())
