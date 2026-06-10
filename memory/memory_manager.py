import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SESSION_ID = str(uuid.uuid4())


class MemoryManager:
    def __init__(self, db_path: str, chroma_path: str):
        self._db_path = db_path
        self._chroma_path = chroma_path
        self._conn: Optional[sqlite3.Connection] = None
        self._collection = None
        self._lock = threading.Lock()
        self._ready = False

    def initialize(self):
        """Blocking init — run once via asyncio.to_thread at startup."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self._chroma_path).mkdir(parents=True, exist_ok=True)
        self._setup_sqlite()
        self._setup_chroma()
        self._ready = True
        log.info("MemoryManager ready (db=%s)", self._db_path)

    def _setup_sqlite(self):
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                app_context TEXT DEFAULT '',
                timestamp   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS facts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                source      TEXT DEFAULT '',
                confidence  REAL DEFAULT 1.0,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
        """)
        self._conn.commit()

    def _setup_chroma(self):
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        client = chromadb.PersistentClient(path=self._chroma_path)
        ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self._collection = client.get_or_create_collection(
            name="memories",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Reads ─────────────────────────────────────────────────────────────────

    def get_relationship_facts(self, limit: int = 12) -> list[str]:
        """Return the most recently updated relationship signals (rel_* keys)."""
        if not self._ready:
            return []
        rows = self._conn.execute(
            "SELECT key, value FROM facts WHERE key LIKE 'rel_%' ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [f"{r['key'][4:]}: {r['value']}" for r in rows]

    def get_recent_turns(self, n: int) -> list[dict]:
        if not self._ready:
            return []
        rows = self._conn.execute(
            "SELECT role, content FROM conversations ORDER BY timestamp DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def search_relevant(self, query: str, k: int) -> list[str]:
        if not self._ready:
            return []
        count = self._collection.count()
        if count == 0:
            return []
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(k, count),
            )
            return results["documents"][0] if results["documents"] else []
        except Exception:
            log.debug("ChromaDB query failed", exc_info=True)
            return []

    # ── Writes ────────────────────────────────────────────────────────────────

    def write_turn(self, role: str, content: str, app_context: str = ""):
        if not self._ready:
            return
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO conversations "
                    "(session_id, role, content, app_context, timestamp) VALUES (?,?,?,?,?)",
                    (SESSION_ID, role, content, app_context, time.time()),
                )
                self._conn.commit()
            except Exception:
                log.exception("write_turn failed")

    def upsert_fact(self, key: str, value: str, source: str = ""):
        if not self._ready:
            return
        with self._lock:
            try:
                now = time.time()
                self._conn.execute(
                    """INSERT INTO facts (key, value, source, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(key) DO UPDATE SET
                           value = excluded.value,
                           source = excluded.source,
                           updated_at = excluded.updated_at""",
                    (key, value, source, now, now),
                )
                self._conn.commit()
                self._collection.upsert(
                    ids=[f"fact_{key}"],
                    documents=[f"{key}: {value}"],
                )
            except Exception:
                log.exception("upsert_fact failed for key=%s", key)

    def add_chunk(self, chunk_id: str, text: str):
        """Index an arbitrary text chunk for semantic retrieval."""
        if not self._ready:
            return
        try:
            self._collection.upsert(ids=[chunk_id], documents=[text])
        except Exception:
            log.debug("add_chunk failed", exc_info=True)
