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

  // Load user profile if a token exists in localStorage
  useEffect(() => {
    if (token) {
      fetchCurrentUser(token);
    }
  }, [token]);

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

  return (
    <div className="app">
      <header className="header">
        <h1>🤖 AI Collaborative Chat Platform</h1>
        <p className="subtitle">Phase 2: Authentication & Foundation</p>
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
