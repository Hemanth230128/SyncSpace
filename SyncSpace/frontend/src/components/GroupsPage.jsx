import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

function GroupsPage({ token, onOpenChat }) {
  const navigate = useNavigate();
  const [groups, setGroups] = useState(() => {
    try {
      const cached = localStorage.getItem("cached_groups");
      return cached ? JSON.parse(cached) : [];
    } catch {
      return [];
    }
  });
  const [groupsLoading, setGroupsLoading] = useState(() => !localStorage.getItem("cached_groups"));
  const [groupsError, setGroupsError] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");
  const [createGroupLoading, setCreateGroupLoading] = useState(false);
  const [expandedGroupIds, setExpandedGroupIds] = useState({});

  // Health checks state
  const [apiStatus, setApiStatus] = useState(null);
  const [dbStatus, setDbStatus] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const authHeaders = () => ({
    Authorization: `Bearer ${token}`,
  });

  const toggleGroupInfo = (groupId, e) => {
    if (e) e.stopPropagation();
    setExpandedGroupIds((prev) => ({
      ...prev,
      [groupId]: !prev[groupId],
    }));
  };

  const fetchGroups = async () => {
    if (groups.length === 0) setGroupsLoading(true);
    setGroupsError("");
    try {
      const res = await fetch("/api/groups", {
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to fetch groups");
      setGroups(data);
      localStorage.setItem("cached_groups", JSON.stringify(data));
    } catch (err) {
      setGroupsError(err.message);
    } finally {
      setGroupsLoading(false);
    }
  };

  useEffect(() => {
    fetchGroups();
  }, []);

  const handleCreateGroup = async (e) => {
    e.preventDefault();
    if (!newGroupName.trim()) return;
    setCreateGroupLoading(true);
    setGroupsError("");
    try {
      const res = await fetch("/api/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          name: newGroupName.trim(),
          description: newGroupDescription.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create group");
      setNewGroupName("");
      setNewGroupDescription("");
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

  const checkHealth = async () => {
    setHealthLoading(true);
    setApiStatus(null);
    setDbStatus(null);

    try {
      const apiRes = await fetch("/api/health");
      const apiData = await apiRes.json();
      setApiStatus(apiData);
    } catch (err) {
      setApiStatus({ status: "unhealthy", detail: err.message });
    }

    try {
      const dbRes = await fetch("/api/health/db");
      const dbData = await dbRes.json();
      setDbStatus(dbData);
    } catch (err) {
      setDbStatus({ status: "unhealthy", detail: err.message });
    } finally {
      setHealthLoading(false);
    }
  };

  const membershipBadge = (status) => {
    if (status === "ADMIN") return <span className="badge admin">👑 Admin</span>;
    if (status === "MEMBER") return <span className="badge member">✅ Member</span>;
    if (status === "PENDING") return <span className="badge pending">⏳ Pending</span>;
    return null;
  };

  const statusColor = (statusObj) => {
    if (!statusObj) return "#9ca3af";
    return statusObj.status === "healthy" ? "#10b981" : "#ef4444";
  };

  return (
    <>
      {/* --- GROUPS LIST & CREATION --- */}
      <section className="groups-section">
        <div className="groups-header">
          <h3>📂 Groups</h3>
        </div>

        {groupsError && <div className="alert error">{groupsError}</div>}

        {/* Create Group Form */}
        <form onSubmit={handleCreateGroup} className="create-group-form">
          <div className="create-group-inputs">
            <input
              type="text"
              placeholder="Group name (e.g. Distributed Systems)..."
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              required
              minLength={1}
              maxLength={100}
              className="create-group-input"
            />
            <input
              type="text"
              placeholder="What will this chat be about? (e.g. Midterm exam prep & syllabus documents)..."
              value={newGroupDescription}
              onChange={(e) => setNewGroupDescription(e.target.value)}
              maxLength={300}
              className="create-group-topic-input"
            />
          </div>
          <button type="submit" disabled={createGroupLoading} className="create-group-btn">
            {createGroupLoading ? "Creating..." : "+ Create Group"}
          </button>
        </form>

        {/* Groups List */}
        {groups.length === 0 && !groupsLoading ? (
          <p className="empty-state">No groups yet. Create one above!</p>
        ) : (
          <div className="groups-list">
            {groups.map((group) => {
              const isMember = group.membership_status === "ADMIN" || group.membership_status === "MEMBER";
              const isExpanded = !!expandedGroupIds[group.id];

              return (
                <div
                  key={group.id}
                  className={`group-card ${isExpanded ? "expanded" : ""}`}
                  onClick={() => toggleGroupInfo(group.id)}
                >
                  <div className="group-card-header">
                    <div className="group-info">
                      <div className="group-title-row">
                        <h4 className="group-name">{group.name}</h4>
                        <button
                          type="button"
                          className={`group-info-toggle-btn ${isExpanded ? "open" : ""}`}
                          onClick={(e) => toggleGroupInfo(group.id, e)}
                          title="Click to view what this chat is about"
                        >
                          ℹ️ About {isExpanded ? "▲" : "▼"}
                        </button>
                      </div>
                      <span className="group-meta">
                        by {group.creator_username} · {new Date(group.created_at).toLocaleDateString()}
                      </span>
                    </div>

                    <div className="group-actions" onClick={(e) => e.stopPropagation()}>
                      {membershipBadge(group.membership_status)}

                      {isMember && (
                        <button
                          className="open-chat-btn"
                          onClick={() => {
                            if (onOpenChat) onOpenChat(group);
                            navigate(`/chat/${group.id}`, { state: { group } });
                          }}
                        >
                          💬 Open Chat →
                        </button>
                      )}

                      {group.membership_status === "PENDING" && (
                        <span className="pending-badge-text">⏳ Pending Approval</span>
                      )}

                      {!group.membership_status && (
                        <button
                          className="join-btn"
                          onClick={() => handleJoinRequest(group.id)}
                        >
                          Request to Join
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Drop Box with info about the group */}
                  {isExpanded && (
                    <div className="group-info-dropbox" onClick={(e) => e.stopPropagation()}>
                      <div className="info-dropbox-badge">
                        <span className="info-icon">🎯</span>
                        <strong>About this chat:</strong>
                      </div>
                      <p className="info-dropbox-text">
                        {group.description && group.description.trim()
                          ? group.description
                          : "General collaborative discussion and document study. No specific topic provided."}
                      </p>
                      {isMember && (
                        <div className="dropbox-actions">
                          <button
                            className="dropbox-enter-btn"
                            onClick={() => {
                              if (onOpenChat) onOpenChat(group);
                              navigate(`/chat/${group.id}`, { state: { group } });
                            }}
                          >
                            💬 Enter Group Chat →
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* --- DEVELOPER SYSTEM HEALTH (COLLAPSIBLE) --- */}
      <details className="health-collapsible">
        <summary className="health-summary">
          ⚙️ Developer System Health Diagnostics (Optional)
        </summary>
        <section className="health-section">
          <div className="health-header">
            <h4>Service Diagnostics</h4>
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
      </details>
    </>
  );
}

export default GroupsPage;
