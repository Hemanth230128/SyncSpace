import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";

function ChatPage({ selectedGroup: propGroup, currentUser, token, onBack, onGroupUpdated }) {
  const { groupId: routeGroupId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const [group, setGroup] = useState(propGroup || location.state?.group || null);
  const [groupLoading, setGroupLoading] = useState(!group);

  const targetGroupId = propGroup?.id || location.state?.group?.id || routeGroupId;
  const [messages, setMessages] = useState(() => {
    try {
      const cached = sessionStorage.getItem(`cached_msgs_${targetGroupId}`);
      return cached ? JSON.parse(cached) : [];
    } catch {
      return [];
    }
  });
  const [messagesLoading, setMessagesLoading] = useState(() => !sessionStorage.getItem(`cached_msgs_${targetGroupId}`));
  const [messageInput, setMessageInput] = useState("");
  const [wsStatus, setWsStatus] = useState("disconnected"); // "connected" | "connecting" | "disconnected"

  // Dropdown states
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [detailsTab, setDetailsTab] = useState("members"); // "members" | "files" | "requests" | "leave"
  const [groupMembers, setGroupMembers] = useState([]);
  const [joinRequests, setJoinRequests] = useState([]);
  const [groupDetailLoading, setGroupDetailLoading] = useState(false);
  const [deleteGroupLoading, setDeleteGroupLoading] = useState(false);

  // Phase 5: Knowledge Base Documents state
  const [documents, setDocuments] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef(null);

  // Phase 6: In-Chat Collaborative AI RAG state
  const [chatTarget, setChatTarget] = useState("chat"); // "chat" | "ai"
  const [aiThinking, setAiThinking] = useState(false);
  const [aiError, setAiError] = useState("");
  const [expandedSources, setExpandedSources] = useState({}); // msgId -> boolean

  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const authHeaders = () => ({
    Authorization: `Bearer ${token}`,
  });

  // If user navigated directly via URL (e.g., /chat/3), fetch group info
  useEffect(() => {
    if (!group && routeGroupId && token) {
      setGroupLoading(true);
      fetch("/api/groups", { headers: authHeaders() })
        .then((res) => (res.ok ? res.json() : []))
        .then((groups) => {
          const match = groups.find((g) => String(g.id) === String(routeGroupId));
          if (match && (match.membership_status === "ADMIN" || match.membership_status === "MEMBER")) {
            setGroup(match);
          } else {
            navigate("/home");
          }
        })
        .catch(() => navigate("/home"))
        .finally(() => setGroupLoading(false));
    }
  }, [routeGroupId, token, group]);

  // Load group documents on mount
  useEffect(() => {
    if (group?.id) {
      fetchDocuments();
    }
  }, [group?.id]);

  // Load group members and pending requests (if admin)
  const fetchGroupDetails = async () => {
    if (!group) return;
    setGroupDetailLoading(true);
    try {
      const fetchMembersPromise = fetch(`/api/groups/${group.id}/members`, {
        headers: authHeaders(),
      }).then((res) => (res.ok ? res.json() : []));

      const fetchRequestsPromise =
        group.membership_status === "ADMIN"
          ? fetch(`/api/groups/${group.id}/requests`, {
              headers: authHeaders(),
            }).then((res) => (res.ok ? res.json() : []))
          : Promise.resolve([]);

      const [membersData, requestsData] = await Promise.all([
        fetchMembersPromise,
        fetchRequestsPromise,
      ]);

      setGroupMembers(membersData);
      setJoinRequests(requestsData);
    } catch (err) {
      console.error("Failed to load group details:", err);
    } finally {
      setGroupDetailLoading(false);
    }
  };

  // Load knowledge base documents for this group
  const fetchDocuments = async () => {
    if (!group) return;
    setDocsLoading(true);
    try {
      const res = await fetch(`/api/groups/${group.id}/documents`, {
        headers: authHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (err) {
      console.error("Failed to load documents:", err);
    } finally {
      setDocsLoading(false);
    }
  };

  // Lazy-load group members, requests, and documents when the dropdown is opened
  useEffect(() => {
    if (group && isDetailsOpen) {
      if (detailsTab === "members" || detailsTab === "requests") {
        fetchGroupDetails();
      } else if (detailsTab === "files") {
        fetchDocuments();
      }
    }
  }, [group?.id, isDetailsOpen, detailsTab]);

  // WebSocket & Message History lifecycle
  useEffect(() => {
    if (!group) return;

    const groupId = group.id;
    let isCancelled = false;

    // Only show loading spinner if no cached messages exist yet
    if (!messages || messages.length === 0) {
      setMessagesLoading(true);
    }

    // 1. Fetch message history
    fetch(`/api/groups/${groupId}/messages`, {
      headers: authHeaders(),
    })
      .then((res) => (res.ok ? res.json() : []))
      .then((history) => {
        if (!isCancelled) {
          setMessages(history);
          setMessagesLoading(false);
          try {
            sessionStorage.setItem(`cached_msgs_${groupId}`, JSON.stringify(history));
          } catch {}
        }
      })
      .catch((err) => {
        console.error("Failed to load message history:", err);
        if (!isCancelled) setMessagesLoading(false);
      });

    // 2. Connect WebSocket
    setWsStatus("connecting");
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/groups/${groupId}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isCancelled) setWsStatus("connected");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.id) {
          setMessages((prev) => {
            // Replace matching pending optimistic message or append
            const pendingIndex = prev.findIndex(
              (m) => m.pending && m.user_id === data.user_id && m.content === data.content
            );
            let updated;
            if (pendingIndex !== -1) {
              updated = [...prev];
              updated[pendingIndex] = data;
            } else if (prev.some((m) => m.id === data.id)) {
              return prev;
            } else {
              updated = [...prev, data];
            }
            try {
              sessionStorage.setItem(`cached_msgs_${groupId}`, JSON.stringify(updated));
            } catch {}
            return updated;
          });
        }
      } catch (err) {
        console.error("Error parsing WebSocket message:", err);
      }
    };

    ws.onclose = () => {
      if (!isCancelled) setWsStatus("disconnected");
    };

    ws.onerror = (err) => {
      console.error("WebSocket encountered an error:", err);
      if (!isCancelled) setWsStatus("disconnected");
    };

    return () => {
      isCancelled = true;
      if (ws) ws.close();
      wsRef.current = null;
    };
  }, [group?.id, token]);

  // Auto-scroll chat to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, aiThinking]);

  const handleBack = () => {
    if (onBack) onBack();
    navigate("/home");
  };

  // Helper to parse message metadata (AI bot response, citations, AI question)
  const parseMessageData = (msg) => {
    const rawContent = msg.content || "";
    const isAiBot = msg.username === "SyncSpace AI" || rawContent.includes("<!--sources:");
    const isAiQuestion = rawContent.startsWith("🤖 @AI:") || rawContent.toLowerCase().startsWith("@ai ");

    let cleanContent = rawContent;
    let sources = [];

    const sourcesMatch = rawContent.match(/<!--sources:(.*?)-->/s);
    if (sourcesMatch) {
      try {
        sources = JSON.parse(sourcesMatch[1]);
        cleanContent = rawContent.replace(/<!--sources:.*?-->/s, "").trim();
      } catch (err) {
        console.error("Error parsing source metadata:", err);
      }
    }

    if (isAiQuestion) {
      cleanContent = cleanContent.replace(/^🤖\s*@AI:\s*/i, "").replace(/^@ai\s*:?\s*/i, "").trim();
    }

    // Remove any robotic [Source 1] tags
    cleanContent = cleanContent.replace(/\[Source\s*\d+[^\]]*\]/gi, "").trim();

    return {
      ...msg,
      isAiBot,
      isAiQuestion,
      cleanContent,
      sources,
    };
  };

  // Handle Message Sending (supports Group Chat and AI Knowledge Base Question)
  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const rawContent = messageInput.trim();
    if (!rawContent) return;

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      alert("Chat connection is not open. Please wait or refresh.");
      return;
    }

    const isAiTarget =
      chatTarget === "ai" ||
      rawContent.toLowerCase().startsWith("@ai") ||
      rawContent.toLowerCase().startsWith("/ask");

    if (isAiTarget) {
      const cleanQuery = rawContent
        .replace(/^@ai\s*:?\s*/i, "")
        .replace(/^\/ask\s*:?\s*/i, "")
        .replace(/^🤖\s*@AI:\s*/i, "")
        .trim();

      if (!cleanQuery) return;

      // 1. FIRST: Instantly send question to the group chat over WebSocket!
      // Everyone in the group receives this immediately and can reply right away!
      const questionFormatted = `🤖 @AI: ${cleanQuery}`;

      const optimisticMsg = {
        id: `optimistic-${Date.now()}-${Math.random()}`,
        group_id: group.id,
        user_id: currentUser?.id,
        username: currentUser?.username || "You",
        content: questionFormatted,
        created_at: new Date().toISOString(),
        pending: true,
      };

      setMessages((prev) => [...prev, optimisticMsg]);
      wsRef.current.send(JSON.stringify({ content: questionFormatted }));
      setMessageInput("");

      // 2. SECOND: Activate AI in background (meanwhile, anyone can answer in chat!)
      setAiThinking(true);
      setAiError("");

      try {
        const res = await fetch(`/api/groups/${group.id}/ask`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...authHeaders(),
          },
          body: JSON.stringify({
            question: cleanQuery,
            already_sent_in_chat: true, // Message was already broadcast via WebSocket
          }),
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Failed to retrieve AI answer");
        }
        // Backend broadcasts AI answer over WebSocket to all group members!
      } catch (err) {
        console.error("Ask AI error:", err);
        setAiError(err.message || "Failed to communicate with AI");
      } finally {
        setAiThinking(false);
      }
    } else {
      // Standard group chat message
      const optimisticMsg = {
        id: `optimistic-${Date.now()}-${Math.random()}`,
        group_id: group.id,
        user_id: currentUser?.id,
        username: currentUser?.username || "You",
        content: rawContent,
        created_at: new Date().toISOString(),
        pending: true,
      };

      setMessages((prev) => [...prev, optimisticMsg]);
      wsRef.current.send(JSON.stringify({ content: rawContent }));
      setMessageInput("");
    }
  };

  const handleQuickAsk = (promptText) => {
    setChatTarget("ai");
    setMessageInput(promptText);
    inputRef.current?.focus();
  };

  const toggleSourcesExpanded = (msgId) => {
    setExpandedSources((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };

  const handleApprove = async (requestId) => {
    try {
      const res = await fetch(`/api/groups/${group.id}/requests/${requestId}/approve`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Failed to approve");
      setJoinRequests((prev) => prev.filter((r) => r.id !== requestId));
      fetchGroupDetails();
      if (onGroupUpdated) onGroupUpdated();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleReject = async (requestId) => {
    try {
      const res = await fetch(`/api/groups/${group.id}/requests/${requestId}/reject`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Failed to reject");
      setJoinRequests((prev) => prev.filter((r) => r.id !== requestId));
      if (onGroupUpdated) onGroupUpdated();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleLeaveGroup = async () => {
    if (group.membership_status === "ADMIN") {
      const confirmDelete = window.confirm(
        `You are an Admin of "${group.name}". As an admin, leaving will permanently delete the group for all members.\n\nDo you want to delete this group instead?`
      );
      if (confirmDelete) {
        handleDeleteGroup();
      }
      return;
    }

    if (!window.confirm(`Are you sure you want to leave "${group.name}"?`)) return;
    try {
      const res = await fetch(`/api/groups/${group.id}/leave`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to leave group");
      }
      try {
        sessionStorage.removeItem(`cached_msgs_${group.id}`);
        const cached = localStorage.getItem("cached_groups");
        if (cached) {
          const list = JSON.parse(cached).filter((g) => g.id !== group.id);
          localStorage.setItem("cached_groups", JSON.stringify(list));
        }
      } catch {}
      if (onGroupUpdated) onGroupUpdated();
      handleBack();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleDeleteGroup = async () => {
    if (!window.confirm(`Are you sure you want to delete "${group.name}"? This cannot be undone.`)) return;
    setDeleteGroupLoading(true);
    try {
      const res = await fetch(`/api/groups/${group.id}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to delete group");
      }
      try {
        sessionStorage.removeItem(`cached_msgs_${group.id}`);
        const cached = localStorage.getItem("cached_groups");
        if (cached) {
          const list = JSON.parse(cached).filter((g) => g.id !== group.id);
          localStorage.setItem("cached_groups", JSON.stringify(list));
        }
      } catch {}
      if (onGroupUpdated) onGroupUpdated();
      handleBack();
    } catch (err) {
      alert(err.message);
    } finally {
      setDeleteGroupLoading(false);
    }
  };

  const handleUploadDocument = async (e) => {
    e.preventDefault();
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;

    setUploadLoading(true);
    setUploadError("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`/api/groups/${group.id}/documents`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Upload failed");
      }
      if (fileInputRef.current) fileInputRef.current.value = "";
      await fetchDocuments();
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploadLoading(false);
    }
  };

  const handleDeleteDocument = async (docId, filename) => {
    if (!window.confirm(`Delete document "${filename}" and its vector chunks?`)) return;
    try {
      const res = await fetch(`/api/groups/${group.id}/documents/${docId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to delete document");
      }
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      alert(err.message);
    }
  };

  if (groupLoading || !group) {
    return (
      <section className="chat-page-section">
        <p className="loading-text" style={{ padding: "40px", textAlign: "center" }}>
          Loading group chat...
        </p>
      </section>
    );
  }

  const readyDocuments = documents.filter((d) => d.status === "READY");

  return (
    <section className="chat-page-section">
      {/* Top Header: Spacious, Uncluttered, Modern 3-Column Layout */}
      <div className="chat-page-header">
        <div className="chat-header-left">
          <button className="back-btn" onClick={handleBack} title="Return to Group List">
            ← Back to Groups
          </button>
        </div>

        <div className="chat-header-center">
          <div className="chat-title-row">
            <h3 className="chat-page-title">#{group.name}</h3>
            <span className={`ws-badge ${wsStatus}`}>
              {wsStatus === "connected" && "🟢 Live"}
              {wsStatus === "connecting" && "🟡 Connecting..."}
              {wsStatus === "disconnected" && "🔴 Offline"}
            </span>
          </div>

          <div className="chat-header-sub">
            {group.description && (
              <span
                className="chat-header-pill chat-topic-pill"
                title={`Chat Topic: ${group.description}`}
                onClick={() => setIsDetailsOpen(true)}
              >
                🎯 {group.description}
              </span>
            )}
            <span
              className="chat-header-pill"
              title="Uploaded PDF documents available for AI grounded answers"
              onClick={() => {
                setIsDetailsOpen(true);
                setDetailsTab("files");
              }}
            >
              📄 {readyDocuments.length} {readyDocuments.length === 1 ? "PDF" : "PDFs"} Indexed
            </span>
            <span className="chat-header-pill ai-active-pill" title="AI questions and answers are shared in the chat with all members">
              ✨ Collaborative AI Chat
            </span>
          </div>
        </div>

        {/* Top-Right Dropdown Menu */}
        <div className="chat-header-right">
          <div className="chat-menu-wrapper">
            <button
              className={`chat-menu-btn ${isDetailsOpen ? "active" : ""}`}
              onClick={() => setIsDetailsOpen(!isDetailsOpen)}
            >
              👥 Group Info ▾
            </button>

            {isDetailsOpen && (
              <div className="chat-details-dropdown">
                {group.description && (
                  <div className="dropdown-topic-banner">
                    <span className="topic-icon">🎯</span>
                    <div className="topic-content">
                      <span className="topic-heading">What this chat is about</span>
                      <p className="topic-text">{group.description}</p>
                    </div>
                  </div>
                )}

                <div className="dropdown-nav">
                  <button
                    className={`dropdown-tab ${detailsTab === "members" ? "active" : ""}`}
                    onClick={() => setDetailsTab("members")}
                    title="Members"
                  >
                    👥 Members ({groupMembers.length})
                  </button>
                  <button
                    className={`dropdown-tab ${detailsTab === "files" ? "active" : ""}`}
                    onClick={() => setDetailsTab("files")}
                    title="Files"
                  >
                    📁 Files {documents.length > 0 ? `(${documents.length})` : ""}
                  </button>
                  <button
                    className={`dropdown-tab ${detailsTab === "requests" ? "active" : ""}`}
                    onClick={() => setDetailsTab("requests")}
                    title="Pending Requests"
                  >
                    📩 Requests {joinRequests.length > 0 ? `(${joinRequests.length})` : ""}
                  </button>
                  <button
                    className={`dropdown-tab danger ${detailsTab === "leave" ? "active" : ""}`}
                    onClick={() => setDetailsTab("leave")}
                    title="Leave or Delete"
                  >
                    🚪 Leave
                  </button>
                  <button
                    className="dropdown-close-btn"
                    onClick={() => setIsDetailsOpen(false)}
                    title="Close menu"
                  >
                    ✕
                  </button>
                </div>

                <div className="dropdown-body">
                  {/* 1. MEMBERS TAB */}
                  {detailsTab === "members" && (
                    <div className="dropdown-members-tab">
                      {groupDetailLoading ? (
                        <p className="loading-text">Loading members...</p>
                      ) : (
                        <ul className="members-list">
                          {groupMembers.map((m) => (
                            <li key={m.user_id} className="member-row">
                              <span className="member-name">
                                {m.username}
                                {currentUser && m.user_id === currentUser.id && " (you)"}
                              </span>
                              <span className={`role-tag ${m.role.toLowerCase()}`}>
                                {m.role === "ADMIN" ? "👑 Admin" : "Member"}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {/* 2. FILES TAB (Knowledge Base Documents) */}
                  {detailsTab === "files" && (
                    <div className="dropdown-files-tab">
                      {/* Admin PDF Upload Form */}
                      {group.membership_status === "ADMIN" ? (
                        <form onSubmit={handleUploadDocument} className="doc-upload-box">
                          <label className="doc-upload-label">
                            📄 <strong>Upload PDF to Knowledge Base</strong>
                          </label>
                          <div className="doc-upload-row">
                            <input
                              type="file"
                              accept=".pdf,application/pdf"
                              ref={fileInputRef}
                              required
                              disabled={uploadLoading}
                              className="doc-file-input"
                            />
                            <button
                              type="submit"
                              disabled={uploadLoading}
                              className="doc-upload-btn"
                            >
                              {uploadLoading ? "Processing..." : "📤 Upload"}
                            </button>
                          </div>
                          {uploadError && <p className="doc-error-text">{uploadError}</p>}
                          <span className="doc-upload-hint">
                            Extracts text & generates pgvector embeddings. All members can query these PDFs directly in chat!
                          </span>
                        </form>
                      ) : (
                        <div className="doc-member-note">
                          📖 <strong>Group Knowledge Base</strong>
                          <p>Documents uploaded by admins are indexed for this group. Anyone in the chat can ask the AI about them!</p>
                        </div>
                      )}

                      {/* Document List */}
                      <div className="docs-list-section">
                        <h6>Uploaded Documents ({documents.length})</h6>
                        {docsLoading ? (
                          <p className="loading-text">Loading documents...</p>
                        ) : documents.length === 0 ? (
                          <div className="empty-docs-state">
                            <span className="empty-docs-icon">📄</span>
                            <p>No documents uploaded yet.</p>
                          </div>
                        ) : (
                          <ul className="docs-list">
                            {documents.map((doc) => (
                              <li key={doc.id} className="doc-row">
                                <div className="doc-info-block">
                                  <div className="doc-title-row">
                                    <span className="doc-icon">📄</span>
                                    <span className="doc-filename" title={doc.filename}>
                                      {doc.filename}
                                    </span>
                                  </div>
                                  <div className="doc-meta-row">
                                    <span className="doc-size">
                                      {(doc.file_size_bytes / 1024).toFixed(1)} KB
                                    </span>
                                    <span>•</span>
                                    <span className="doc-date">
                                      {new Date(doc.created_at).toLocaleDateString()}
                                    </span>
                                    <span>•</span>
                                    <span className={`doc-status-badge ${doc.status.toLowerCase()}`}>
                                      {doc.status === "READY" && `✅ Ready (${doc.chunk_count} chunks)`}
                                      {doc.status === "PROCESSING" && "⏳ Processing..."}
                                      {doc.status === "FAILED" && "❌ Failed"}
                                    </span>
                                  </div>
                                  {doc.status === "FAILED" && doc.error_message && (
                                    <p className="doc-error-inline" title={doc.error_message}>
                                      ⚠️ {doc.error_message}
                                    </p>
                                  )}
                                </div>

                                {group.membership_status === "ADMIN" && (
                                  <button
                                    className="doc-delete-btn"
                                    onClick={() => handleDeleteDocument(doc.id, doc.filename)}
                                    title="Delete document and its chunks"
                                  >
                                    🗑️
                                  </button>
                                )}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                  )}

                  {/* 3. PENDING REQUESTS TAB */}
                  {detailsTab === "requests" && (
                    <div className="dropdown-requests-tab">
                      {group.membership_status === "ADMIN" ? (
                        groupDetailLoading ? (
                          <p className="loading-text">Loading requests...</p>
                        ) : joinRequests.length === 0 ? (
                          <div className="empty-requests-state">
                            <span className="empty-requests-icon">✉️</span>
                            <p>No pending join requests.</p>
                          </div>
                        ) : (
                          <ul className="requests-list">
                            {joinRequests.map((req) => (
                              <li key={req.id} className="request-row">
                                <span className="request-user">👤 {req.username}</span>
                                <div className="request-actions">
                                  <button
                                    className="approve-btn"
                                    onClick={() => handleApprove(req.id)}
                                  >
                                    Approve
                                  </button>
                                  <button
                                    className="reject-btn"
                                    onClick={() => handleReject(req.id)}
                                  >
                                    Reject
                                  </button>
                                </div>
                              </li>
                            ))}
                          </ul>
                        )
                      ) : (
                        <div className="admin-only-notice">
                          <span className="notice-icon">🔒</span>
                          <h4>Admin Access Required</h4>
                          <p>Only group administrators can view and manage pending join requests.</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 4. LEAVE TAB */}
                  {detailsTab === "leave" && (
                    <div className="dropdown-leave-tab">
                      {group.membership_status === "ADMIN" ? (
                        <div className="leave-card admin-alert">
                          <div className="leave-card-badge">👑 Group Administrator</div>
                          <h4>Delete Group Instead</h4>
                          <p>
                            You are an <strong>Admin</strong> of <strong>#{group.name}</strong>.
                            Admins cannot leave a group without deleting it. Leaving will permanently delete this group and all its messages for all members.
                          </p>
                          <button
                            className="delete-group-action-btn"
                            onClick={handleDeleteGroup}
                            disabled={deleteGroupLoading}
                          >
                            {deleteGroupLoading ? "Deleting..." : "🗑️ Delete Group"}
                          </button>
                        </div>
                      ) : (
                        <div className="leave-card member-alert">
                          <div className="leave-card-badge">👤 Member</div>
                          <h4>Leave Group</h4>
                          <p>
                            Are you sure you want to leave <strong>#{group.name}</strong>?
                            You will no longer receive real-time messages and will need an admin to approve your request if you wish to rejoin.
                          </p>
                          <button className="leave-group-action-btn" onClick={handleLeaveGroup}>
                            🚪 Confirm & Leave Group
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Unified Collaborative Chat Stream */}
      <div className="chat-messages-container dedicated">
        {messagesLoading ? (
          <p className="loading-text">Loading message history...</p>
        ) : messages.length === 0 ? (
          <div className="empty-chat-state">
            <span className="empty-chat-icon">💬✨</span>
            <h4>Welcome to #{group.name}!</h4>
            <p>
              This is a shared group space where members chat and ask the AI questions about uploaded documents.
              Everyone can see what others ask and learn from the AI's answers!
            </p>
            {readyDocuments.length > 0 && (
              <div className="chat-starter-prompts">
                <span className="starter-label">Try asking the AI:</span>
                <div className="starter-chips">
                  <button
                    type="button"
                    className="starter-chip"
                    onClick={() => {
                      setMessageInput("What are the main topics covered in our uploaded documents?");
                      inputRef.current?.focus();
                    }}
                  >
                    "What are the main topics in our documents?"
                  </button>
                  <button
                    type="button"
                    className="starter-chip"
                    onClick={() => {
                      setMessageInput("Summarize the key requirements or action items.");
                      inputRef.current?.focus();
                    }}
                  >
                    "Summarize key requirements or action items."
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="chat-messages-list">
            {messages.map((msg) => {
              const parsed = parseMessageData(msg);
              const isSelf = currentUser && msg.user_id === currentUser.id;

              // 1. AI BOT RESPONSE MESSAGE
              if (parsed.isAiBot) {
                const primaryDocName = parsed.sources && parsed.sources.length > 0 ? parsed.sources[0].filename : null;
                return (
                  <div key={msg.id} className="chat-message-row ai-bot-row">
                    <div className="chat-ai-card">
                      <div className="chat-ai-header">
                        <div className="chat-ai-brand">
                          <div className="chat-ai-avatar">🤖</div>
                          <div>
                            <div className="chat-ai-name">
                              SyncSpace AI
                              <span className="chat-ai-badge">AI Teacher</span>
                            </div>
                            <span className="chat-ai-timestamp">
                              {new Date(msg.created_at).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                          </div>
                        </div>
                        {primaryDocName ? (
                          <span className="chat-ai-grounded-pill" title={`Source: ${primaryDocName}`}>
                            📄 {primaryDocName}
                          </span>
                        ) : (
                          <span className="chat-ai-grounded-pill">
                            📚 Group Knowledge
                          </span>
                        )}
                      </div>

                      <div className="chat-ai-body">
                        {parsed.cleanContent}
                      </div>
                    </div>
                  </div>
                );
              }

              // 2. USER QUESTION DIRECTED TO AI
              if (parsed.isAiQuestion) {
                return (
                  <div
                    key={msg.id}
                    className={`chat-message-row ${isSelf ? "self" : "other"}`}
                  >
                    <div className={`chat-message-bubble ${isSelf ? "self" : "other"} ai-question-bubble`}>
                      <div className="chat-message-meta">
                        <span className="chat-sender">
                          {isSelf ? "You" : msg.username}
                          <span className="ai-question-tag">💡 Asked AI</span>
                        </span>
                        <span className="chat-time">
                          {new Date(msg.created_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>
                      <div className="chat-content">
                        <span className="ai-question-prefix">@AI: </span>
                        {parsed.cleanContent}
                      </div>
                    </div>
                  </div>
                );
              }

              // 3. REGULAR CHAT MESSAGE
              return (
                <div
                  key={msg.id}
                  className={`chat-message-row ${isSelf ? "self" : "other"}`}
                >
                  <div className={`chat-message-bubble ${isSelf ? "self" : "other"}`}>
                    <div className="chat-message-meta">
                      <span className="chat-sender">
                        {isSelf ? "You" : msg.username}
                      </span>
                      <span className="chat-time">
                        {new Date(msg.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                    <div className="chat-content">{parsed.cleanContent}</div>
                  </div>
                </div>
              );
            })}

            {/* In-Chat AI Thinking Animation */}
            {aiThinking && (
              <div className="chat-message-row ai-bot-row">
                <div className="chat-ai-thinking-card">
                  <div className="thinking-avatar">🤖</div>
                  <div className="thinking-text-block">
                    <div className="thinking-title">
                      SyncSpace AI is preparing an explanation
                      <span className="thinking-dots">
                        <span>.</span><span>.</span><span>.</span>
                      </span>
                    </div>
                    <div className="thinking-sub">
                      Reading group PDFs and breaking it down in clear, easy words for everyone
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* AI Error Notification Banner */}
      {aiError && (
        <div className="chat-ai-error-banner">
          <div className="error-text">
            <strong>⚠️ AI Error:</strong> {aiError}
          </div>
          <button className="error-dismiss-btn" onClick={() => setAiError("")}>
            ✕
          </button>
        </div>
      )}

      {/* Smart Suggestions Chips (when documents are available) */}
      {readyDocuments.length > 0 && (
        <div className="chat-quick-hints">
          <span className="hint-label">✨ Quick Ask:</span>
          <button
            type="button"
            className="hint-chip"
            onClick={() => handleQuickAsk("Summarize the key takeaways and decisions in our documents.")}
          >
            "Summarize key takeaways"
          </button>
          <button
            type="button"
            className="hint-chip"
            onClick={() => handleQuickAsk("What are the important deadlines, dates, or specifications mentioned?")}
          >
            "Important dates & specs"
          </button>
        </div>
      )}

      {/* Input Bar with Left Select Option (Chat vs Ask AI) & Single Send Button */}
      <form onSubmit={handleSendMessage} className="chat-input-form dedicated">
        {/* Left: Instant Binary Toggle Button (Chat vs Ask AI) */}
        <div className="chat-binary-toggle-wrapper">
          <button
            type="button"
            className={`chat-binary-toggle-btn ${chatTarget === "ai" ? "ai-active" : "chat-active"}`}
            onClick={() => setChatTarget((prev) => (prev === "ai" ? "chat" : "ai"))}
            title={
              chatTarget === "ai"
                ? "AI Teacher Mode is ON (Click to switch to normal Chat)"
                : "Normal Chat Mode (Click to switch to Ask AI Teacher)"
            }
          >
            {chatTarget === "ai" ? (
              <>
                <span className="toggle-badge-icon">🤖</span>
                <span className="toggle-badge-text">Ask AI</span>
              </>
            ) : (
              <>
                <span className="toggle-badge-icon">💬</span>
                <span className="toggle-badge-text">Chat</span>
              </>
            )}
          </button>
        </div>

        {/* Center: Input field */}
        <div className="chat-input-wrapper">
          <input
            ref={inputRef}
            type="text"
            placeholder={
              chatTarget === "ai"
                ? `Ask AI teacher about group documents (shared with everyone)...`
                : `Message #${group.name}...`
            }
            value={messageInput}
            onChange={(e) => setMessageInput(e.target.value)}
            disabled={wsStatus !== "connected"}
            className="chat-input"
            autoFocus
          />
          {messageInput && (
            <button
              type="button"
              className="chat-input-clear-btn"
              onClick={() => setMessageInput("")}
              title="Clear text"
            >
              ✕
            </button>
          )}
        </div>

        {/* Right: Single Send Button */}
        <div className="chat-input-actions">
          <button
            type="submit"
            disabled={wsStatus !== "connected" || !messageInput.trim()}
            className={`chat-send-btn ${chatTarget === "ai" ? "ai-active" : ""}`}
            title={chatTarget === "ai" ? "Send question to group chat and trigger AI" : "Send message to group chat"}
          >
            Send 🚀
          </button>
        </div>
      </form>
    </section>
  );
}

export default ChatPage;
