# Backend Plan — Python / FastAPI

## Language & Runtime
- Python 3.13
- FastAPI + uvicorn
- uv for dependency management (no pip, no requirements.txt)

---

## Embedding Strategy — Priority Controlled by `.env`

**No code change needed to switch provider — just update `.env`.**

| Provider | Model | Dimensions | Cost | Needs API key? |
|---|---|---|---|---|
| **BGE** (default) | `BAAI/bge-large-en-v1.5` | 1024 | Free tier available | Yes — `HUGGINGFACE_API_KEY` |
| **OpenAI** (fallback) | `text-embedding-3-small` | 1536 | Paid | Yes — `OPENAI_API_KEY` |

BGE is used via **HuggingFace Inference API** — no model downloaded locally or on server.
Model is called over HTTP using a URL + token. Nothing stored on disk.

**`.env` controls everything:**
```env
EMBEDDING_PROVIDER=bge      # switch to "openai" to flip priority
HUGGINGFACE_API_KEY=hf_...  # get from huggingface.co/settings/tokens
HUGGINGFACE_MODEL_URL=https://api-inference.huggingface.co/models/BAAI/bge-large-en-v1.5
EMBEDDING_DIM=1024           # must match: bge=1024, openai=1536
```

**Fallback behaviour:**
```
EMBEDDING_PROVIDER=bge
    → Try BGE first
        ↓ success          ↓ fails (no torch, hub down, etc.)
    Use BGE            Try OpenAI automatically
                           ↓ success     ↓ fails
                       Use OpenAI    Raise error

EMBEDDING_PROVIDER=openai  → same logic, reversed
```

**Important:** If you switch provider, you must also:
1. Update `EMBEDDING_DIM` to match
2. Run Alembic migration (vector column dimension changes)
3. Re-process all documents (old embeddings are in wrong dimensional space)

```bash
alembic revision --autogenerate -m "update embedding dimension"
alembic upgrade head
```

---

## Database — Supabase (PostgreSQL + pgvector)

**Why Supabase:**
- PostgreSQL + pgvector already set up — no server to manage
- pgvector replaces FAISS — vectors stored permanently, survive restarts
- Free tier covers development and demos
- Standard PostgreSQL connection string — SQLAlchemy and Alembic work unchanged
- Dashboard to view and query data visually

**Free tier limits:**
| Limit | Free |
|---|---|
| Storage | 500MB |
| Inactivity | Pauses after 1 week (unpause manually) |
| Projects | 2 |
| Bandwidth | 5GB/month |

**Upgrade to Pro ($25/month) when going to production with real users.**

---

## Environment Variables — `.env` File

Create a `.env` file in the project root. **Never commit this to git** (already in `.gitignore`).

```env
# OpenAI
OPENAI_API_KEY=sk-...

# Supabase — get these from Supabase dashboard → Project Settings → Database
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres

# Supabase API (for Supabase client if needed)
SUPABASE_URL=https://[YOUR-PROJECT-REF].supabase.co
SUPABASE_ANON_KEY=eyJ...

# App settings
APP_ENV=development
APP_PORT=8001

# Ingestion limits (change these anytime — no code changes needed)
MAX_FILE_SIZE_MB=15
MAX_FILES_PER_SESSION=3
```

**Where to find each value in Supabase dashboard:**
- `DATABASE_URL` → Project Settings → Database → Connection string (URI)
- `SUPABASE_URL` → Project Settings → API → Project URL
- `SUPABASE_ANON_KEY` → Project Settings → API → anon public key
- `MAX_FILE_SIZE_MB` / `MAX_FILES_PER_SESSION` → set by you, change anytime

---

## Vector Store Strategy — Primary + Fallback

**Primary (always):** pgvector on Supabase
**Fallback (automatic):** ChromaDB — only used if pgvector connection fails

```
App starts
    ↓
Try connect to Supabase pgvector
    ↓ success                        ↓ fails (Supabase down, no internet, credentials wrong)
Use pgvector                         Use ChromaDB (local disk)
(persistent, production)             (logs a WARNING so you know)
                                     Data persists to disk — survives restarts
```

**Why ChromaDB as fallback (not FAISS):**
- ChromaDB persists to disk — data is not lost if the server restarts
- FAISS is in-memory only — all data gone on restart
- ChromaDB's LangChain API is nearly identical to pgvector — easy to swap

**Code pattern (in `app/services/vector_store.py`):**
```python
import logging

def get_vector_store():
    try:
        # Always try pgvector first
        store = connect_pgvector()
        logging.info("Vector store: pgvector (Supabase)")
        return store
    except Exception as e:
        # Automatic fallback — log warning so team knows
        logging.warning(f"pgvector unavailable ({e}), falling back to ChromaDB")
        return connect_chromadb()
```

**Add to pyproject.toml dependencies:**
- `chromadb` (fallback vector store)

**ChromaDB local storage path:** `./chroma_data/` (add to `.dockerignore` and `.gitignore`)

---

## Phase 1 — uv + Docker Foundation (DONE)

- `pyproject.toml` + `uv.lock` replace `requirements.txt`
- `Dockerfile` — Python 3.13-slim + uv
- Anyone clones and runs — no manual install needed

---

## Phase 2 — FastAPI Backend

**Run command:**
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

**Target folder structure:**
```
app/
├── __init__.py
├── main.py              # FastAPI app instance, mounts routers + static files
├── routers/
│   ├── chat.py          # POST /chat
│   └── upload.py        # POST /upload
├── services/
│   ├── rag.py           # answer_question(), process_input()
│   └── vector_store.py  # pgvector setup (replaces FAISS)
├── models/
│   ├── schemas.py       # Pydantic request/response models
│   └── db.py            # SQLAlchemy table definitions
├── db/
│   └── session.py       # SQLAlchemy engine + session
└── static/              # Frontend files served by FastAPI
    └── index.html
```

**API endpoints:**
```
GET  /           → serves frontend (index.html)
POST /upload     → accepts PDF/DOCX/TXT/PPTX → returns { session_id }
POST /chat       → { session_id, question } → returns { answer }
GET  /health     → { status: "ok" } for Docker/AWS health checks
```

---

## RAG Pipeline — 4 Steps

```
1. INGESTION      →    2. STORING         →    3. RETRIEVAL        →    4. LLM ANSWER
   Files + URLs             pgvector                MMR search                OpenAI GPT-4o-mini
   parsed &                 (Supabase)              diverse, non-             generates answer
   chunked                  ChromaDB                redundant chunks          from retrieved
                            fallback                from pgvector             context
```

**Step 3 — Retrieval method: MMR (Maximum Marginal Relevance)**

MMR picks chunks that are both relevant to the question AND different from each other.
Without MMR, top-3 results could be 3 near-identical paragraphs — wasting context space.

Tunable via `.env` — no code changes needed:
```env
RETRIEVAL_K=3        # chunks sent to LLM (more = richer context, slower + costlier)
RETRIEVAL_FETCH_K=10 # candidate pool MMR picks from (must be >= RETRIEVAL_K)
RETRIEVAL_LAMBDA=0.7 # 1.0 = pure similarity · 0.0 = pure diversity · 0.7 = balanced
```

**Future upgrade (Phase 4): Hybrid Search**
Combine vector similarity + keyword search (BM25) for even better accuracy on documents
with specific terms, names, or numbers.

---

## Step 1 — Ingestion

### File Upload
- **Supported formats:** TXT, DOC, DOCX, PDF
- **Max file size:** controlled by `MAX_FILE_SIZE_MB` in `.env` (default: 15MB)
- **Max files per session:** controlled by `MAX_FILES_PER_SESSION` in `.env` (default: 3)
- **Upload mode:** all files uploaded at once in parallel — not one at a time
- Limits are in `.env` so they can be changed later without touching code

**Document Parsing — LiteParse v2:**
- Package: `liteparse` (`pip install liteparse`)
- Made by LlamaIndex, fully open source
- Rewritten in Rust — up to 100x faster than alternatives
- Runs completely locally — no API key, no cloud, no cost
- Single parser handles all 4 formats
- Replaces: `PyPDF2`, `python-docx`, `python-pptx` from old codebase

### URL Scraping
- User pastes a link in the chat → app scrapes the content → goes through same RAG pipeline as files
- **Primary scraper: Crawl4AI** — handles both plain HTML and JS-rendered pages (React, Vue, Angular), built for RAG/AI use cases
- **Fallback: Playwright** — used automatically if Crawl4AI fails (Playwright is already installed as Crawl4AI's dependency)

```
User pastes URL
    ↓
Try Crawl4AI (primary)
    ↓ success                        ↓ fails
Use extracted text               Try Playwright (fallback)
                                     ↓ success        ↓ fails
                                 Use extracted text   Return error to user
```

### API Endpoint (JSON)
- User pastes an API URL that returns JSON data
- Headers are **optional** — user fills them in only if the API requires authentication
- If no headers needed (public API) — leave headers empty

**Example inputs:**
```
API URL:  https://api.example.com/products
Headers:  Authorization: Bearer <token>    ← optional, leave blank if not needed
          Content-Type: application/json   ← optional
```

**How it works:**
```
User pastes API URL + optional headers
    ↓
httpx GET request to the API
    ↓ success                          ↓ fails (bad URL, auth error, timeout)
JSON response received             Return error to user with reason
    ↓
Extract all text values from JSON
(recursively flattens nested JSON)
    ↓
Goes through same RAG pipeline as files
```

**Library:** `httpx` — free, async-ready, works perfectly with FastAPI

**Dependencies to add to pyproject.toml:**
- `fastapi`
- `uvicorn[standard]`
- `python-multipart` (for file uploads)
- `liteparse` (document parser — replaces PyPDF2 + python-docx)
- `crawl4ai` (primary URL scraper — handles JS pages)
- `playwright` (fallback URL scraper — auto-installed with crawl4ai)
- `httpx` (API endpoint fetch — async HTTP client)
- `sqlalchemy`
- `alembic`
- `psycopg2-binary` (PostgreSQL driver)
- `pgvector` (pgvector SQLAlchemy type)
- `langchain-community` (PGVector vectorstore)
- `chromadb` (fallback vector store)

**Known bug to fix in this phase:**
`dataAssistant.py` imports `langchain_classic` which is NOT a real PyPI package.
```python
# Wrong (does not exist):
from langchain_classic.chains import RetrievalQA
from langchain_classic.memory import ConversationSummaryBufferMemory

# Correct:
from langchain.chains import RetrievalQA
from langchain.memory import ConversationSummaryBufferMemory
```

---

## Phase 2b — Alembic Database Migrations

**What Alembic does:** You define tables in Python (SQLAlchemy models), Alembic creates
and updates them in Supabase automatically. Change a model → run one command → database updated.

**Setup (one time):**
```bash
uv run alembic init alembic
```

**Every time you change a model:**
```bash
uv run alembic revision --autogenerate -m "describe your change"
uv run alembic upgrade head
```

**Tables we will create:**
```
sessions       — id, created_at
documents      — id, session_id, filename, file_type, uploaded_at
embeddings     — id, document_id, content, embedding (vector), created_at
chat_history   — id, session_id, role, message, created_at
```

---

## Phase 4 — Feature Improvements (Backend)

- Switch from `gpt-4` to `gpt-4o-mini` (faster + cheaper, same quality for RAG)
- Replace deprecated LangChain classes with latest:
  - `ChatOpenAI` → `langchain_openai.ChatOpenAI`
  - `OpenAIEmbeddings` → `langchain_openai.OpenAIEmbeddings`
  - `RetrievalQA` → LCEL chain with `RunnableWithMessageHistory`
- Streaming responses via Server-Sent Events (SSE)
- Support more file types: CSV, Excel, Markdown
- Multi-document session support

---

## Phase 5 — AWS Deployment

- Push Docker image to Amazon ECR
- Deploy on ECS Fargate (serverless — no servers to manage)
- Supabase remains the database (no AWS RDS needed)
- `.env` credentials stored in AWS Secrets Manager
- Load balancer + HTTPS via ACM certificate

```bash
# Build and push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin <ecr-url>
docker build -t rag-assistant .
docker tag rag-assistant:latest <ecr-url>/rag-assistant:latest
docker push <ecr-url>/rag-assistant:latest
```

**Dockerfile CMD (Phase 2 onwards):**
```dockerfile
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```
