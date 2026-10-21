import { useState, useEffect } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import "./App.css";
import AuthPage from "./components/AuthPage";
import GroupsPage from "./components/GroupsPage";
import ChatPage from "./components/ChatPage";

function App() {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("token") || null);
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const cached = localStorage.getItem("user");
      return cached ? JSON.parse(cached) : null;
    } catch {
      return null;
    }
  });
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [authChecking, setAuthChecking] = useState(() => !!token && !localStorage.getItem("user"));

  // Validate token and silently sync profile in background
  useEffect(() => {
    if (token) {
      fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((res) => {
          if (res.ok) return res.json();
          throw new Error("Invalid token");
        })
        .then((userData) => {
          setCurrentUser(userData);
          localStorage.setItem("user", JSON.stringify(userData));
        })
        .catch(() => {
          handleLogout();
        })
        .finally(() => {
          setAuthChecking(false);
        });
    } else {
      setAuthChecking(false);
    }
  }, [token]);

  const handleLoginSuccess = (newToken, userData) => {
    setToken(newToken);
    setCurrentUser(userData);
    localStorage.setItem("user", JSON.stringify(userData));
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setToken(null);
    setCurrentUser(null);
    setIsProfileOpen(false);
    navigate("/login");
  };

  if (authChecking) {
    return (
      <div className="app">
        <p className="loading-text" style={{ padding: "40px", textAlign: "center" }}>
          Authenticating...
        </p>
      </div>
    );
  }

  return (
    <div className="app">
      {/* --- Top Navigation Header --- */}
      <header className="navbar-header">
        <div className="brand-section">
          <h1>🤖 SyncSpace</h1>
          <p className="subtitle">AI Collaborative Chat Platform</p>
        </div>

        {/* Top-Right Profile Dropdown Pill */}
        {currentUser && (
          <div className="profile-widget-wrapper">
            <button
              className={`profile-avatar-pill ${isProfileOpen ? "active" : ""}`}
              onClick={() => setIsProfileOpen(!isProfileOpen)}
              title="User Profile"
            >
              <span className="profile-pill-avatar">
                {currentUser.username.charAt(0).toUpperCase()}
              </span>
              <span className="profile-pill-name">{currentUser.username}</span>
              <span className="profile-pill-arrow">▾</span>
            </button>

            {isProfileOpen && (
              <div className="profile-dropdown-menu">
                <div className="profile-menu-header">
                  <div className="profile-menu-avatar">
                    {currentUser.username.charAt(0).toUpperCase()}
                  </div>
                  <div className="profile-menu-info">
                    <h4>{currentUser.username}</h4>
                    <span className="profile-user-id">User ID: #{currentUser.id}</span>
                  </div>
                  <button
                    className="profile-close-btn"
                    onClick={() => setIsProfileOpen(false)}
                    title="Close"
                  >
                    ✕
                  </button>
                </div>

                <div className="profile-menu-details">
                  <div className="profile-meta-row">
                    <span className="meta-label">Joined</span>
                    <span className="meta-value">
                      {new Date(currentUser.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="profile-meta-row">
                    <span className="meta-label">Status</span>
                    <span className="meta-badge-jwt">🔐 Authenticated</span>
                  </div>
                </div>

                <div className="profile-menu-footer">
                  <button onClick={handleLogout} className="profile-logout-btn">
                    Log Out
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </header>

      {/* --- Routed Page Views --- */}
      <Routes>
        <Route
          path="/login"
          element={
            currentUser ? (
              <Navigate to="/home" replace />
            ) : (
              <AuthPage onLoginSuccess={handleLoginSuccess} />
            )
          }
        />

        <Route
          path="/home"
          element={
            currentUser ? (
              <GroupsPage token={token} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        <Route
          path="/chat/:groupId"
          element={
            currentUser ? (
              <ChatPage currentUser={currentUser} token={token} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Fallback & Root redirect */}
        <Route
          path="/"
          element={<Navigate to={currentUser ? "/home" : "/login"} replace />}
        />
        <Route
          path="*"
          element={<Navigate to={currentUser ? "/home" : "/login"} replace />}
        />
      </Routes>
    </div>
  );
}

export default App;
