# RAG Data Assistant — Master Plan

## Goal
Transform the current single-file Streamlit prototype into a production-ready,
containerized RAG application that runs identically on any laptop or cloud server.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, uvicorn |
| AI / RAG | OpenAI GPT-4o, LangChain, FAISS |
| Frontend (Stage A) | Plain HTML + CSS + JavaScript |
| Frontend (Stage B) | React + Tailwind CSS + Vite |
| Packaging | uv + pyproject.toml + uv.lock |
| Container | Docker (Python 3.13-slim) |
| Cloud | AWS (ECR + ECS Fargate) |

---

## Phase Overview

| Phase | What | Status |
|---|---|---|
| 1 | uv + Docker foundation | **Done** |
| 2 | FastAPI backend (`app/main.py`, port 8001) | Next |
| 3 | Frontend — plain HTML/JS (Stage A), React later (Stage B) | Planned |
| 4 | Feature improvements (streaming, more file types, GPT-4o) | Planned |
| 5 | AWS deployment (ECR + ECS Fargate) | Planned |

---

## How to Run (always one command)

```bash
# Local development
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Docker
docker build -t rag-assistant .
docker run -p 8001:8001 --env-file .env rag-assistant
```

---

## Detailed Plans

- Backend details → [PLAN-backend.md](PLAN-backend.md)
- Frontend details → [PLAN-frontend.md](PLAN-frontend.md)

---

## Environment Variables

Create a `.env` file (never commit to git):
```
OPENAI_API_KEY=sk-...
```
