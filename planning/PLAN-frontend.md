# Frontend Plan — HTML/JS → React

## Decision
We are NOT using Streamlit. It cannot serve as an API and is not suitable
for a production chatbot.

---

## Stage A — Plain HTML + CSS + JavaScript

**When:** Phase 3, built alongside the FastAPI backend.

**Why start here:**
- Zero build tools, zero npm, zero setup
- FastAPI serves the HTML file directly — one command runs everything
- Backend can be tested and validated before investing in React

**Folder structure:**
```
app/
└── static/
    ├── index.html    # Chat UI
    ├── style.css     # Styling
    └── chat.js       # fetch() calls to POST /chat and POST /upload
```

**FastAPI mounts it with one line:**
```python
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
```

**User opens:** `http://localhost:8001` — sees the chat UI.

**What the UI does:**
- File upload (drag and drop or button) → calls `POST /upload`
- Chat input → calls `POST /chat` with session_id + question
- Displays responses in a chat bubble layout

**Run command (everything, one command):**
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

---

## Stage B — React + Tailwind CSS + Vite

**When:** After Stage A is working and UI needs to grow (components, routing, auth).

**Why React:**
- Industry standard — every developer knows it
- Reusable components (ChatBubble, FileUpload, MessageList)
- Tailwind for fast, clean styling
- Vite for fast builds (much faster than Create React App)

**Folder structure:**
```
frontend/
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── ChatWindow.tsx
│   │   ├── MessageBubble.tsx
│   │   └── FileUpload.tsx
│   └── api/
│       └── client.ts       # all fetch() calls to FastAPI
├── package.json
└── vite.config.ts
```

**How many commands to run:**

| Situation | Commands | Detail |
|---|---|---|
| Stage A, any env | **1** | FastAPI serves static files directly |
| Stage B, development | **1** | `make dev` — Makefile starts both together |
| Stage B, Docker / AWS | **1** | React pre-built into `app/static/`, FastAPI serves it |

**Makefile for development (1 command):**
```makefile
dev:
    uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload &
    cd frontend && npm run dev
```

**Production build flow:**
```bash
cd frontend && npm run build   # outputs to app/static/
docker build -t rag-assistant .  # FastAPI serves the built files
```

**Bottom line:** Always one command, whether running locally or on AWS.
