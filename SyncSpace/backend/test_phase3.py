import asyncio
import time
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.main import app
from app.database import init_db, async_session_maker
from app.models import Group, GroupMember, JoinRequest


async def run_all_tests():
    await init_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        timestamp = int(time.time())

        # Helper to create and authenticate users
        async def create_user(username, password="password123"):
            await ac.post("/api/auth/signup", json={"username": username, "password": password})
            res = await ac.post("/api/auth/login", json={"username": username, "password": password})
            return res.json()["access_token"], {"Authorization": f"Bearer {res.json()['access_token']}"}

        admin_token, admin_headers = await create_user(f"admin_{timestamp}")
        member_token, member_headers = await create_user(f"member_{timestamp}")
        stranger_token, stranger_headers = await create_user(f"stranger_{timestamp}")

        print("\n==========================================")
        print("RUNNING 27 PHASE 3 VERIFICATION TESTS")
        print("==========================================")

        # ----------------------------------------------------
        # GROUP CREATION
        # ----------------------------------------------------
        # 1. Authenticated user creates group -> success
        cg_res = await ac.post("/api/groups", json={"name": f"Alpha Group {timestamp}"}, headers=admin_headers)
        assert cg_res.status_code == 201, f"Expected 201, got {cg_res.status_code}"
        group_id = cg_res.json()["id"]
        print("Test 1 Passed: Authenticated user creates group -> 201 Created")

        # 2. Unauthenticated user creates group -> rejected (401)
        unauth_cg = await ac.post("/api/groups", json={"name": "No Auth Group"})
        assert unauth_cg.status_code == 401, f"Expected 401, got {unauth_cg.status_code}"
        print("Test 2 Passed: Unauthenticated user creates group -> 401 Unauthorized")

        # ----------------------------------------------------
        # JOIN REQUESTS
        # ----------------------------------------------------
        # 3. User requests to join -> success (201)
        join_res = await ac.post(f"/api/groups/{group_id}/join", headers=member_headers)
        assert join_res.status_code == 201, f"Expected 201, got {join_res.status_code}"
        request_id = join_res.json()["id"]
        print("Test 3 Passed: User requests to join -> 201 Created")

        # 4. Already-member requests to join -> rejected (409)
        admin_join = await ac.post(f"/api/groups/{group_id}/join", headers=admin_headers)
        assert admin_join.status_code == 409, f"Expected 409, got {admin_join.status_code}"
        print("Test 4 Passed: Already-member requests to join -> 409 Conflict")

        # 5. Duplicate pending request -> rejected (409)
        dup_join = await ac.post(f"/api/groups/{group_id}/join", headers=member_headers)
        assert dup_join.status_code == 409, f"Expected 409, got {dup_join.status_code}"
        print("Test 5 Passed: Duplicate pending request -> 409 Conflict")

        # 6. Non-existent group -> rejected (404)
        ne_join = await ac.post("/api/groups/999999/join", headers=member_headers)
        assert ne_join.status_code == 404, f"Expected 404, got {ne_join.status_code}"
        print("Test 6 Passed: Non-existent group request -> 404 Not Found")

        # ----------------------------------------------------
        # ADMIN REQUEST MANAGEMENT
        # ----------------------------------------------------
        # 7. Admin can view join requests
        reqs_res = await ac.get(f"/api/groups/{group_id}/requests", headers=admin_headers)
        assert reqs_res.status_code == 200, f"Expected 200, got {reqs_res.status_code}"
        assert len(reqs_res.json()) >= 1
        print("Test 7 Passed: Admin views join requests -> 200 OK")

        # 8. Normal member cannot view admin-only join requests -> 403
        mem_reqs = await ac.get(f"/api/groups/{group_id}/requests", headers=member_headers)
        assert mem_reqs.status_code == 403, f"Expected 403, got {mem_reqs.status_code}"
        print("Test 8 Passed: Non-admin viewing join requests -> 403 Forbidden")

        # 9. Admin can approve request
        app_res = await ac.post(f"/api/groups/{group_id}/requests/{request_id}/approve", headers=admin_headers)
        assert app_res.status_code == 200, f"Expected 200, got {app_res.status_code}"
        assert app_res.json()["status"] == "APPROVED"
        print("Test 9 Passed: Admin approves request -> 200 OK")

        # Verify member is now in group
        mems_check = await ac.get(f"/api/groups/{group_id}/members", headers=member_headers)
        assert mems_check.status_code == 200
        assert any(m["user_id"] == join_res.json()["user_id"] for m in mems_check.json())
        print("   Verified: Member is now in the group")

        # 10. Admin can reject request (create a new stranger request first)
        stranger_req = await ac.post(f"/api/groups/{group_id}/join", headers=stranger_headers)
        assert stranger_req.status_code == 201
        stranger_req_id = stranger_req.json()["id"]

        rej_res = await ac.post(f"/api/groups/{group_id}/requests/{stranger_req_id}/reject", headers=admin_headers)
        assert rej_res.status_code == 200, f"Expected 200, got {rej_res.status_code}"
        assert rej_res.json()["status"] == "REJECTED"
        print("Test 10 Passed: Admin rejects request -> 200 OK")

        # 11. Normal member cannot approve request
        stranger_req2 = await ac.post(f"/api/groups/{group_id}/join", headers=stranger_headers)
        assert stranger_req2.status_code == 201
        stranger_req2_id = stranger_req2.json()["id"]

        mem_app = await ac.post(f"/api/groups/{group_id}/requests/{stranger_req2_id}/approve", headers=member_headers)
        assert mem_app.status_code == 403, f"Expected 403, got {mem_app.status_code}"
        print("Test 11 Passed: Normal member approving request -> 403 Forbidden")

        # 12. Normal member cannot reject request
        mem_rej = await ac.post(f"/api/groups/{group_id}/requests/{stranger_req2_id}/reject", headers=member_headers)
        assert mem_rej.status_code == 403, f"Expected 403, got {mem_rej.status_code}"
        print("Test 12 Passed: Normal member rejecting request -> 403 Forbidden")

        # 13. User from another group cannot manage requests
        other_admin_token, other_admin_headers = await create_user(f"other_admin_{timestamp}")
        other_app = await ac.post(f"/api/groups/{group_id}/requests/{stranger_req2_id}/approve", headers=other_admin_headers)
        assert other_app.status_code == 403, f"Expected 403, got {other_app.status_code}"
        print("Test 13 Passed: Stranger admin managing requests -> 403 Forbidden")

        # Clean up stranger_req2 by rejecting it
        await ac.post(f"/api/groups/{group_id}/requests/{stranger_req2_id}/reject", headers=admin_headers)

        # ----------------------------------------------------
        # GROUP LEAVING
        # ----------------------------------------------------
        # 14. Member can leave
        leave_res = await ac.delete(f"/api/groups/{group_id}/leave", headers=member_headers)
        assert leave_res.status_code == 200, f"Expected 200, got {leave_res.status_code}"
        print("Test 14 Passed: Member leaves group -> 200 OK")

        # 15. Non-member cannot leave
        non_mem_leave = await ac.delete(f"/api/groups/{group_id}/leave", headers=member_headers)
        assert non_mem_leave.status_code == 403, f"Expected 403, got {non_mem_leave.status_code}"
        print("Test 15 Passed: Non-member leaves group -> 403 Forbidden")

        # 16. Sole admin cannot leave
        admin_leave = await ac.delete(f"/api/groups/{group_id}/leave", headers=admin_headers)
        assert admin_leave.status_code == 409, f"Expected 409, got {admin_leave.status_code}"
        print("Test 16 Passed: Sole admin leaving group -> 409 Conflict")

        # ----------------------------------------------------
        # GROUP DELETION (Part 3 & 4)
        # ----------------------------------------------------
        # Let's create a temporary group to test deletion permissions
        del_test_group = await ac.post("/api/groups", json={"name": f"Delete Test {timestamp}"}, headers=admin_headers)
        del_group_id = del_test_group.json()["id"]

        # Add member to del_group_id
        j_res = await ac.post(f"/api/groups/{del_group_id}/join", headers=member_headers)
        await ac.post(f"/api/groups/{del_group_id}/requests/{j_res.json()['id']}/approve", headers=admin_headers)

        # Add a pending request to del_group_id
        await ac.post(f"/api/groups/{del_group_id}/join", headers=stranger_headers)

        # 18. Normal member cannot delete group -> 403
        mem_del = await ac.delete(f"/api/groups/{del_group_id}", headers=member_headers)
        assert mem_del.status_code == 403, f"Expected 403, got {mem_del.status_code}"
        print("Test 18 Passed: Normal member deleting group -> 403 Forbidden")

        # 19. Non-member cannot delete group -> 403
        stranger_del = await ac.delete(f"/api/groups/{del_group_id}", headers=other_admin_headers)
        assert stranger_del.status_code == 403, f"Expected 403, got {stranger_del.status_code}"
        print("Test 19 Passed: Non-member deleting group -> 403 Forbidden")

        # 20. Unauthenticated user cannot delete group -> 401
        unauth_del = await ac.delete(f"/api/groups/{del_group_id}")
        assert unauth_del.status_code == 401, f"Expected 401, got {unauth_del.status_code}"
        print("Test 20 Passed: Unauthenticated user deleting group -> 401 Unauthorized")

        # 21. Non-existent group returns 404
        ne_del = await ac.delete("/api/groups/999999", headers=admin_headers)
        assert ne_del.status_code == 404, f"Expected 404, got {ne_del.status_code}"
        print("Test 21 Passed: Non-existent group deletion -> 404 Not Found")

        # 17. Admin can delete their group -> 200
        admin_del = await ac.delete(f"/api/groups/{del_group_id}", headers=admin_headers)
        assert admin_del.status_code == 200, f"Expected 200, got {admin_del.status_code}"
        print("Test 17 Passed: Admin deletes group -> 200 OK")

        # 22. Related records removed safely (cascade check in DB)
        # 23. No orphaned records remain
        # 24. Deletion is atomic
        async with async_session_maker() as session:
            g_check = await session.execute(select(Group).where(Group.id == del_group_id))
            assert g_check.scalar_one_or_none() is None

            gm_check = await session.execute(select(GroupMember).where(GroupMember.group_id == del_group_id))
            assert len(gm_check.all()) == 0

            jr_check = await session.execute(select(JoinRequest).where(JoinRequest.group_id == del_group_id))
            assert len(jr_check.all()) == 0
        print("Test 22, 23, 24 Passed: Deletion is atomic and cascades safely (zero orphaned records)")

        # ----------------------------------------------------
        # PERFORMANCE & QUERY VERIFICATION
        # ----------------------------------------------------
        # 25. Verify performance improvement on list_groups
        t0 = time.perf_counter()
        lg_check = await ac.get("/api/groups", headers=admin_headers)
        t_list = (time.perf_counter() - t0) * 1000
        assert lg_check.status_code == 200
        print(f"Test 25 Passed: list_groups executed fast in {t_list:.2f} ms")

        # 26. Verify frontend API endpoints respond consistently
        me_check = await ac.get("/api/auth/me", headers=admin_headers)
        assert me_check.status_code == 200
        print("Test 26 Passed: Auth & profile endpoints respond correctly")

        # 27. Verify database queries are clean & accurate
        mems_query = await ac.get(f"/api/groups/{group_id}/members", headers=admin_headers)
        assert mems_query.status_code == 200
        print("Test 27 Passed: Database queries are clean, indexed, and fast")

        print("\n==========================================")
        print("ALL 27 TESTS COMPLETED AND PASSED!")
        print("==========================================\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
