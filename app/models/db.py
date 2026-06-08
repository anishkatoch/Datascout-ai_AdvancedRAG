from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from datetime import datetime, timezone
from dotenv import load_dotenv
import uuid
import os

load_dotenv()

# Dimension must match the active embedding provider:
#   BAAI/bge-large-en-v1.5 → 1024
#   OpenAI text-embedding-3-small → 1536
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

Base = declarative_base()


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    source = Column(String, nullable=False, default="file")  # "file", "url", "api"
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
