# AI Collaborative Chat Platform

A Discord-like real-time messaging platform with AI-powered features.

> **Current status:** Foundation setup — health-check only.

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **PostgreSQL** running on `localhost:5432`

## Quick Start

### 1. Database

Create the PostgreSQL database:

```sql
CREATE DATABASE ai_chat_platform;
```

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Edit `.env` if your PostgreSQL credentials differ from the defaults.

Start the server:

```bash
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and click **Check Health**.

## Project Structure

```
ai-chat-platform/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app + CORS
│   │   ├── config.py        # Env var loading
│   │   ├── database.py      # Async SQLAlchemy setup
│   │   └── routers/
│   │       └── health.py    # Health-check endpoints
│   ├── .env                 # Local secrets (gitignored)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Health dashboard UI
│   │   └── main.jsx         # React entry point
│   ├── vite.config.js       # Dev server + API proxy
│   └── package.json
└── README.md
```
