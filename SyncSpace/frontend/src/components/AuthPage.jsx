import { useState } from "react";
import { useNavigate } from "react-router-dom";

function AuthPage({ onLoginSuccess }) {
  const navigate = useNavigate();
  const [authMode, setAuthMode] = useState("login"); // "login" | "signup"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authSuccess, setAuthSuccess] = useState("");

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

      setAuthSuccess("Account created successfully! You can now log in.");
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

      // Fetch user profile
      const userRes = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${receivedToken}` },
      });

      if (!userRes.ok) {
        throw new Error("Failed to load user profile");
      }

      const userData = await userRes.json();
      onLoginSuccess(receivedToken, userData);
      navigate("/home");
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  return (
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
  );
}

export default AuthPage;
