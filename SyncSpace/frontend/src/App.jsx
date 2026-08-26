import { useState } from "react";
import "./App.css";

function App() {
  const [apiStatus, setApiStatus] = useState(null);
  const [dbStatus, setDbStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  const checkHealth = async () => {
    setLoading(true);
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

    setLoading(false);
  };

  const statusColor = (status) => {
    if (!status) return "gray";
    if (status.status === "healthy") return "green";
    return "red";
  };

  return (
    <div className="app">
      <h1>🤖 AI Collaborative Chat Platform</h1>
      <p className="subtitle">Foundation Health Dashboard</p>

      <button onClick={checkHealth} disabled={loading} className="check-btn">
        {loading ? "Checking..." : "Check Health"}
      </button>

      <div className="cards">
        <div className="card" style={{ borderColor: statusColor(apiStatus) }}>
          <h2>API Status</h2>
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
          <h2>Database Status</h2>
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
    </div>
  );
}

export default App;
