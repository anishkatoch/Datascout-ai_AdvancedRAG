import logging
import os
from langchain_openai import OpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector
from langchain_chroma import Chroma

logger = logging.getLogger(__name__)


def _build_database_url() -> str:
    from urllib.parse import quote_plus
    host     = os.getenv("DB_HOST")
    port     = os.getenv("DB_PORT", "5432")
    user     = quote_plus(os.getenv("DB_USER", ""))
    password = quote_plus(os.getenv("DB_PASSWORD", ""))  # handles special chars like @, #, $
    name     = os.getenv("DB_NAME")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def get_embeddings():
    provider = os.getenv("EMBEDDING_PROVIDER", "bge").lower()
    logger.info(f"[EMBED] Provider priority: {provider}")
    if provider == "bge":
        return _try_bge() or _try_openai()
    else:
        return _try_openai() or _try_bge()


def _try_bge():
    try:
        from langchain_huggingface import HuggingFaceEndpointEmbeddings
        embeddings = HuggingFaceEndpointEmbeddings(
            model=os.getenv("HUGGINGFACE_MODEL_ID"),
            huggingfacehub_api_token=os.getenv("HUGGINGFACE_API_KEY"),
        )
        logger.info("[EMBED] Using BAAI/bge-large-en-v1.5 (HuggingFace Inference API, 1024 dims)")
        return embeddings
    except Exception as e:
        logger.warning(f"[EMBED] BGE unavailable ({e})")
        return None


def _try_openai():
    try:
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
        logger.info("[EMBED] Using text-embedding-3-small (OpenAI, 1536 dims)")
        return embeddings
    except Exception as e:
        logger.warning(f"[EMBED] OpenAI unavailable ({e})")
        return None


def get_vector_store(session_id: str):
    logger.info(f"[STORE] Initialising vector store — session={session_id}")
    embeddings = get_embeddings()
    if not embeddings:
        logger.error("[STORE] No embedding provider available")
        raise RuntimeError("No embedding provider available. Check HUGGINGFACE_API_KEY or OPENAI_API_KEY.")

    collection = f"session_{session_id}"

    try:
        store = PGVector(
            embeddings=embeddings,
            collection_name=collection,
            connection=_build_database_url(),
        )
        logger.info(f"[STORE] Connected to pgvector (Supabase) — collection={collection}")
        return store
    except Exception as e:
        logger.warning(f"[STORE] pgvector unavailable ({e}) — falling back to ChromaDB")
        store = Chroma(
            collection_name=collection,
            embedding_function=embeddings,
            persist_directory="./chroma_data",
        )
        logger.info(f"[STORE] Using ChromaDB (local) — collection={collection}")
        return store
