import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.core.logging_config import setup_logging
from app.routers import chat, upload, auth as auth_router
from app.services import auth_service

load_dotenv(override=True)
setup_logging()

logger = logging.getLogger(__name__)

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Routes that do NOT require authentication
_PUBLIC_PREFIXES = ("/auth", "/health", "/auth.html", "/auth.css", "/auth.js")
_PROTECTED_PREFIXES = ("/chat/", "/upload/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Server starting...")
    yield
    logger.info("Server shutting down.")


app = FastAPI(
    title="RAG Data Assistant",
    description="Chat with your documents using AI",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Auth middleware ────────────────────────────────────────────────────────────

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Only enforce auth on protected API routes
    if any(path.startswith(p) for p in _PROTECTED_PREFIXES):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else None
        if not token:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        user = auth_service.verify_token(token)
        if not user:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)
        request.state.user = user

    return await call_next(request)


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(auth_router.router)
app.include_router(upload.router)
app.include_router(chat.router)

if os.getenv("WHATSAPP_ENABLED", "false").lower() == "true":
    from app.routers import whatsapp
    app.include_router(whatsapp.router)
    logger.info("WhatsApp webhook active at /whatsapp/webhook")


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve auth.html explicitly so the browser can reach it
@app.get("/auth.html")
def serve_auth():
    return FileResponse(os.path.join(_STATIC_DIR, "auth.html"))


app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
