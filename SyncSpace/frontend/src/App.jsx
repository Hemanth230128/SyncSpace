import { useState, useEffect } from "react";
import "./App.css";

function App() {
  // --- Auth State ---
  const [token, setToken] = useState(() => localStorage.getItem("token") || null);
  const [currentUser, setCurrentUser] = useState(null);
  const [authMode, setAuthMode] = useState("login"); // "login" | "signup"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authSuccess, setAuthSuccess] = useState("");

  // --- Health State ---
  const [apiStatus, setApiStatus] = useState(null);
  const [dbStatus, setDbStatus] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);

  // --- Groups State ---
  const [groups, setGroups] = useState([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupsError, setGroupsError] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [createGroupLoading, setCreateGroupLoading] = useState(false);

  // --- Selected Group State ---
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [groupMembers, setGroupMembers] = useState([]);
  const [joinRequests, setJoinRequests] = useState([]);
  const [groupDetailLoading, setGroupDetailLoading] = useState(false);

  // Load user profile if a token exists in localStorage
  useEffect(() => {
    if (token) {
      fetchCurrentUser(token);
    }
  }, [token]);

  // Load groups when user is logged in
  useEffect(() => {
    if (currentUser && token) {
      fetchGroups();
    }
  }, [currentUser]);

  // --- Auth helpers (unchanged from Phase 2) ---

  const authHeaders = (authToken) => ({
    Authorization: `Bearer ${authToken || token}`,
  });

  const fetchCurrentUser = async (authToken) => {
    try {
      const response = await fetch("/api/auth/me", {
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      });

      if (response.ok) {
        const userData = await response.json();
        setCurrentUser(userData);
        setAuthError("");
      } else {
        // Token is invalid or expired
        handleLogout();
      }
    } catch (err) {
      setAuthError("Failed to fetch user profile: " + err.message);
    }
  };

  const handleSignup = async (e) => {
    e.preventDefault();
    setAuthError("");
    setAuthSuccess("");
    setAuthLoading(true);

    try {
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Signup failed");
      }

      setAuthSuccess(`Account created for "${data.username}"! You can now log in.`);
      setAuthMode("login");
      setPassword("");
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError("");
    setAuthSuccess("");
    setAuthLoading(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Login failed");
      }

      const receivedToken = data.access_token;
      localStorage.setItem("token", receivedToken);
      setToken(receivedToken);
      setUsername("");
      setPassword("");
      await fetchCurrentUser(receivedToken);
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setCurrentUser(null);
    setAuthError("");
    setAuthSuccess("");
    setGroups([]);
    setSelectedGroup(null);
    setGroupMembers([]);
    setJoinRequests([]);
  };

  // --- Health Check Handler ---
  const checkHealth = async () => {
    setHealthLoading(true);
    setApiStatus(null);
    setDbStatus(null);

    // 1. Check API health
    try {
      const apiRes = await fetch("/api/health");
      const apiData = await apiRes.json();
      setApiStatus(apiData);
    } catch (err) {
      setApiStatus({ status: "unreachable", detail: err.message });
    }

    // 2. Check database health
    try {
      const dbRes = await fetch("/api/health/db");
      const dbData = await dbRes.json();
      setDbStatus(dbData);
    } catch (err) {
      setDbStatus({ status: "unreachable", detail: err.message });
    }

    setHealthLoading(false);
  };

  const statusColor = (status) => {
    if (!status) return "#ccc";
    if (status.status === "healthy") return "#16a34a";
    return "#dc2626";
  };

  // =====================================================================
  // GROUPS LOGIC (Phase 3)
  // =====================================================================

  const fetchGroups = async () => {
    setGroupsLoading(true);
    setGroupsError("");
    try {
      const res = await fetch("/api/groups", { headers: authHeaders() });
      if (!res.ok) throw new Error("Failed to load groups");
      const data = await res.json();
      setGroups(data);
    } catch (err) {
      setGroupsError(err.message);
    } finally {
      setGroupsLoading(false);
    }
  };

  const handleCreateGroup = async (e) => {
    e.preventDefault();
    if (!newGroupName.trim()) return;
    setCreateGroupLoading(true);
    setGroupsError("");
    try {
      const res = await fetch("/api/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ name: newGroupName.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create group");
      setNewGroupName("");
      await fetchGroups();
    } catch (err) {
      setGroupsError(err.message);
    } finally {
      setCreateGroupLoading(false);
    }
  };

  const handleJoinRequest = async (groupId) => {
    setGroupsError("");
    try {
      const res = await fetch(`/api/groups/${groupId}/join`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to request join");
      await fetchGroups();
    } catch (err) {
      setGroupsError(err.message);
    }
  };

  const handleSelectGroup = async (group) => {
    if (selectedGroup && selectedGroup.id === group.id) {
      setSelectedGroup(null);
      setGroupMembers([]);
      setJoinRequests([]);
      return;
    }

    setGroupDetailLoading(true);
    setSelectedGroup(group);
    setGroupMembers([]);
    setJoinRequests([]);

    // Only fetch details if user is a member
    if (group.membership_status === "ADMIN" || group.membership_status === "MEMBER") {
      try {
        const membersRes = await fetch(`/api/groups/${group.id}/members`, {
          headers: authHeaders(),
        });
        if (membersRes.ok) {
          setGroupMembers(await membersRes.json());
        }
      } catch (err) {
        /* ignore */
      }

      // Fetch join requests only if admin
      if (group.membership_status === "ADMIN") {
        try {
          const reqsRes = await fetch(`/api/groups/${group.id}/requests`, {
            headers: authHeaders(),
          });
          if (reqsRes.ok) {
            setJoinRequests(await reqsRes.json());
          }
        } catch (err) {
          /* ignore */
        }
      }
    }
    setGroupDetailLoading(false);
  };

  const handleApprove = async (groupId, requestId) => {
    try {
      const res = await fetch(`/api/groups/${groupId}/requests/${requestId}/approve`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to approve");
      await fetchGroups();
      // Refresh the selected group's details
      const updatedGroup = groups.find((g) => g.id === groupId);
      if (updatedGroup) {
        await handleSelectGroup({ ...updatedGroup, membership_status: "ADMIN" });
      }
    } catch (err) {
      setGroupsError(err.message);
    }
  };

  const handleReject = async (groupId, requestId) => {
    try {
      const res = await fetch(`/api/groups/${groupId}/requests/${requestId}/reject`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to reject");
      await fetchGroups();
      const updatedGroup = groups.find((g) => g.id === groupId);
      if (updatedGroup) {
        await handleSelectGroup({ ...updatedGroup, membership_status: "ADMIN" });
      }
    } catch (err) {
      setGroupsError(err.message);
    }
  };

  const handleLeaveGroup = async (groupId) => {
    setGroupsError("");
    try {
      const res = await fetch(`/api/groups/${groupId}/leave`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to leave group");
      setSelectedGroup(null);
      setGroupMembers([]);
      setJoinRequests([]);
      await fetchGroups();
    } catch (err) {
      setGroupsError(err.message);
    }
  };

  // --- Render helpers ---

  const membershipBadge = (status) => {
    if (status === "ADMIN") return <span className="badge admin">👑 Admin</span>;
    if (status === "MEMBER") return <span className="badge member">✅ Member</span>;
    if (status === "PENDING") return <span className="badge pending">⏳ Pending</span>;
    return null;
  };

  return (
    <div className="app">
      <header className="header">
        <h1>🤖 AI Collaborative Chat Platform</h1>
        <p className="subtitle">Phase 3: Groups, Membership & Roles</p>
      </header>

      {/* --- AUTHENTICATION SECTION --- */}
      <section className="auth-section">
        {currentUser ? (
          // Logged In View
          <div className="logged-in-box">
            <div className="user-avatar">
              {currentUser.username.charAt(0).toUpperCase()}
            </div>
            <h2>Welcome, <span className="highlight-username">{currentUser.username}</span>!</h2>
            <div className="user-details">
              <p><strong>User ID:</strong> {currentUser.id}</p>
              <p><strong>Username:</strong> {currentUser.username}</p>
              <p>
                <strong>Member Since:</strong>{" "}
                {new Date(currentUser.created_at).toLocaleString()}
              </p>
              <p className="auth-status-badge">🔐 Authenticated with JWT</p>
            </div>
            <button onClick={handleLogout} className="logout-btn">
              Log Out
            </button>
          </div>
        ) : (
          // Logged Out (Signup / Login) View
          <div className="auth-card">
            <div className="auth-tabs">
              <button
                className={`tab-btn ${authMode === "login" ? "active" : ""}`}
                onClick={() => {
                  setAuthMode("login");
                  setAuthError("");
                  setAuthSuccess("");
                }}
              >
                Log In
              </button>
              <button
                className={`tab-btn ${authMode === "signup" ? "active" : ""}`}
                onClick={() => {
                  setAuthMode("signup");
                  setAuthError("");
                  setAuthSuccess("");
                }}
              >
                Sign Up
              </button>
            </div>

            <form
              onSubmit={authMode === "login" ? handleLogin : handleSignup}
              className="auth-form"
            >
              <h3>{authMode === "login" ? "Log in to your account" : "Create a new account"}</h3>

              {authError && <div className="alert error">{authError}</div>}
              {authSuccess && <div className="alert success">{authSuccess}</div>}

              <div className="form-group">
                <label htmlFor="username">Username</label>
                <input
                  id="username"
                  type="text"
                  placeholder="Enter username (min 3 chars)"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  minLength={3}
                  maxLength={50}
                  autoComplete="username"
                />
              </div>

              <div className="form-group">
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  placeholder="Enter password (min 6 chars)"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  maxLength={100}
                  autoComplete={authMode === "login" ? "current-password" : "new-password"}
                />
              </div>

              <button type="submit" disabled={authLoading} className="auth-submit-btn">
                {authLoading
                  ? "Processing..."
                  : authMode === "login"
                  ? "Log In"
                  : "Sign Up"}
              </button>
            </form>
          </div>
        )}
      </section>

      {/* --- GROUPS SECTION (visible only when logged in) --- */}
      {currentUser && (
        <section className="groups-section">
          <div className="groups-header">
            <h3>📂 Groups</h3>
            <button onClick={fetchGroups} disabled={groupsLoading} className="check-btn">
              {groupsLoading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {groupsError && <div className="alert error">{groupsError}</div>}

          {/* Create Group Form */}
          <form onSubmit={handleCreateGroup} className="create-group-form">
            <input
              type="text"
              placeholder="New group name..."
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              required
              minLength={1}
              maxLength={100}
              className="create-group-input"
            />
            <button type="submit" disabled={createGroupLoading} className="create-group-btn">
              {createGroupLoading ? "Creating..." : "+ Create Group"}
            </button>
          </form>

          {/* Groups List */}
          {groups.length === 0 && !groupsLoading ? (
            <p className="empty-state">No groups yet. Create one above!</p>
          ) : (
            <div className="groups-list">
              {groups.map((group) => (
                <div
                  key={group.id}
                  className={`group-card ${selectedGroup && selectedGroup.id === group.id ? "selected" : ""}`}
                >
                  <div className="group-card-header" onClick={() => handleSelectGroup(group)}>
                    <div className="group-info">
                      <h4 className="group-name">{group.name}</h4>
                      <span className="group-meta">
                        by {group.creator_username} · {new Date(group.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="group-actions">
                      {membershipBadge(group.membership_status)}
                      {!group.membership_status && (
                        <button
                          className="join-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleJoinRequest(group.id);
                          }}
                        >
                          Request to Join
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Expanded Group Detail Panel */}
                  {selectedGroup && selectedGroup.id === group.id && (
                    <div className="group-detail-panel">
                      {groupDetailLoading ? (
                        <p className="loading-text">Loading details...</p>
                      ) : group.membership_status === "ADMIN" || group.membership_status === "MEMBER" ? (
                        <>
                          {/* Members */}
                          <div className="detail-block">
                            <h5>👥 Members ({groupMembers.length})</h5>
                            {groupMembers.length === 0 ? (
                              <p className="empty-state">No members found.</p>
                            ) : (
                              <ul className="members-list">
                                {groupMembers.map((m) => (
                                  <li key={m.user_id} className="member-row">
                                    <span className="member-name">
                                      {m.username}
                                      {m.user_id === currentUser.id && " (you)"}
                                    </span>
                                    <span className={`role-tag ${m.role.toLowerCase()}`}>
                                      {m.role === "ADMIN" ? "👑 Admin" : "Member"}
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>

                          {/* Pending Join Requests (Admin only) */}
                          {group.membership_status === "ADMIN" && (
                            <div className="detail-block">
                              <h5>📩 Pending Requests ({joinRequests.length})</h5>
                              {joinRequests.length === 0 ? (
                                <p className="empty-state">No pending requests.</p>
                              ) : (
                                <ul className="requests-list">
                                  {joinRequests.map((req) => (
                                    <li key={req.id} className="request-row">
                                      <span className="request-user">{req.username}</span>
                                      <span className="request-date">
                                        {new Date(req.created_at).toLocaleDateString()}
                                      </span>
                                      <div className="request-actions">
                                        <button
                                          className="approve-btn"
                                          onClick={() => handleApprove(group.id, req.id)}
                                        >
                                          ✅ Approve
                                        </button>
                                        <button
                                          className="reject-btn"
                                          onClick={() => handleReject(group.id, req.id)}
                                        >
                                          ❌ Reject
                                        </button>
                                      </div>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          )}

                          {/* Leave Group */}
                          <div className="detail-block leave-block">
                            <button
                              className="leave-btn"
                              onClick={() => handleLeaveGroup(group.id)}
                            >
                              🚪 Leave Group
                            </button>
                          </div>
                        </>
                      ) : group.membership_status === "PENDING" ? (
                        <p className="pending-message">⏳ Your join request is pending admin approval.</p>
                      ) : (
                        <p className="not-member-message">You are not a member of this group.</p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* --- SYSTEM HEALTH DASHBOARD SECTION --- */}
      <section className="health-section">
        <div className="health-header">
          <h3>System Health Checks</h3>
          <button onClick={checkHealth} disabled={healthLoading} className="check-btn">
            {healthLoading ? "Checking..." : "Run Health Check"}
          </button>
        </div>

        <div className="cards">
          <div className="card" style={{ borderColor: statusColor(apiStatus) }}>
            <h4>API Service</h4>
            {apiStatus ? (
              <>
                <p className={`status ${apiStatus.status}`}>
                  {apiStatus.status === "healthy" ? "✅ Healthy" : "❌ " + apiStatus.status}
                </p>
                {apiStatus.service && <p className="detail">{apiStatus.service}</p>}
                {apiStatus.detail && <p className="detail error">{apiStatus.detail}</p>}
              </>
            ) : (
              <p className="status pending">—</p>
            )}
          </div>

          <div className="card" style={{ borderColor: statusColor(dbStatus) }}>
            <h4>PostgreSQL Database</h4>
            {dbStatus ? (
              <>
                <p className={`status ${dbStatus.status}`}>
                  {dbStatus.status === "healthy" ? "✅ Connected" : "❌ " + (dbStatus.database || dbStatus.status)}
                </p>
                {dbStatus.detail && <p className="detail error">{dbStatus.detail}</p>}
              </>
            ) : (
              <p className="status pending">—</p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

export default App;
