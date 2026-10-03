"""
memory_bank.py - Memory and context management system for CHOTU AI assistant.

Stores conversations, entities, facts, and projects in a local SQLite database.
Thread-safe via threading.Lock. Auto-creates database tables on initialization.
"""

import sqlite3
import datetime
import uuid
import threading
import logging
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryBank:
    """
    Persistent memory and context manager for CHOTU AI.

    Uses SQLite for local storage of conversations, entities, facts, and
    project metadata.  All public methods are thread-safe.
    """

    # Path is relative to the repository root so it works regardless of cwd.
    DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "chotu_memory.db"

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize MemoryBank, creating the database file and schema if needed.

        Args:
            db_path: Optional override for the SQLite database file path.
                     Defaults to ``data/chotu_memory.db`` under the project root.
        """
        self._lock = threading.Lock()
        self._db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH

        # Ensure the parent directory exists.
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("MemoryBank: initializing database at %s", self._db_path)
        self._init_database()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Return a new SQLite connection with row_factory set."""
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")  # Better concurrent write safety
        return conn

    def _init_database(self) -> None:
        """Create all required tables if they do not already exist."""
        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                session_id  TEXT    NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS entities (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                type        TEXT    NOT NULL,
                description TEXT,
                updated_at  TEXT    NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS facts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT    NOT NULL UNIQUE,
                value       TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                status      TEXT    NOT NULL DEFAULT 'active',
                description TEXT,
                created_at  TEXT    NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);",
            "CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversations(timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);",
            "CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);",
        ]

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    for stmt in ddl_statements:
                        conn.execute(stmt)
                logger.debug("MemoryBank: database schema verified.")
            except sqlite3.Error as exc:
                logger.exception("MemoryBank: failed to initialize schema: %s", exc)
                raise
            finally:
                conn.close()

    @staticmethod
    def _now_iso() -> str:
        """Return the current UTC time as an ISO-8601 string."""
        return datetime.datetime.utcnow().isoformat()

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    def add_conversation(self, role: str, content: str, session_id: str) -> int:
        """
        Append a single message to the conversations table.

        Args:
            role:       Speaker role, e.g. ``'user'`` or ``'assistant'``.
            content:    The message text.
            session_id: UUID string identifying the current chat session.

        Returns:
            The row id of the newly inserted record.
        """
        sql = (
            "INSERT INTO conversations (timestamp, role, content, session_id) "
            "VALUES (?, ?, ?, ?)"
        )
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.execute(sql, (self._now_iso(), role, content, session_id))
                    row_id: int = cur.lastrowid  # type: ignore[assignment]
                logger.debug("MemoryBank: added conversation row %d", row_id)
                return row_id
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.add_conversation error: %s", exc)
                raise
            finally:
                conn.close()

    def get_recent_conversations(self, n: int = 20) -> List[Dict[str, Any]]:
        """
        Retrieve the *n* most recent conversation rows across all sessions.

        Args:
            n: Maximum number of rows to return (default 20).

        Returns:
            List of dicts with keys ``id``, ``timestamp``, ``role``,
            ``content``, ``session_id``.  Ordered oldest-first.
        """
        sql = (
            "SELECT id, timestamp, role, content, session_id "
            "FROM conversations "
            "ORDER BY id DESC "
            "LIMIT ?"
        )
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(sql, (n,)).fetchall()
                result = [dict(r) for r in reversed(rows)]
                return result
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.get_recent_conversations error: %s", exc)
                return []
            finally:
                conn.close()

    def get_conversation_context(self, n: int = 10) -> str:
        """
        Return the last *n* messages formatted as a prompt context string.

        Each line has the format ``ROLE: content``.

        Args:
            n: Number of most-recent messages to include (default 10).

        Returns:
            Multi-line string suitable for prepending to an LLM prompt.
        """
        messages = self.get_recent_conversations(n)
        lines: List[str] = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def clear_session(self, session_id: str) -> int:
        """
        Delete all conversation records belonging to *session_id*.

        Args:
            session_id: The session UUID to purge.

        Returns:
            Number of rows deleted.
        """
        sql = "DELETE FROM conversations WHERE session_id = ?"
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.execute(sql, (session_id,))
                    deleted: int = cur.rowcount
                logger.info("MemoryBank: cleared %d rows for session %s", deleted, session_id)
                return deleted
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.clear_session error: %s", exc)
                return 0
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Entity management
    # ------------------------------------------------------------------

    def remember_entity(self, name: str, entity_type: str, description: str) -> None:
        """
        Insert or update a named entity in the entities table.

        Args:
            name:        Unique entity name (e.g. ``'John'``).
            entity_type: Category string (e.g. ``'person'``, ``'place'``).
            description: Free-text description or notes about the entity.
        """
        sql = (
            "INSERT INTO entities (name, type, description, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "  type        = excluded.type, "
            "  description = excluded.description, "
            "  updated_at  = excluded.updated_at"
        )
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(sql, (name, entity_type, description, self._now_iso()))
                logger.debug("MemoryBank: remembered entity '%s'", name)
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.remember_entity error: %s", exc)
            finally:
                conn.close()

    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single entity by name (case-insensitive prefix search).

        Args:
            name: Entity name to look up.

        Returns:
            Dict with keys ``id``, ``name``, ``type``, ``description``,
            ``updated_at``, or ``None`` if not found.
        """
        sql = (
            "SELECT id, name, type, description, updated_at "
            "FROM entities "
            "WHERE LOWER(name) = LOWER(?) "
            "LIMIT 1"
        )
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(sql, (name,)).fetchone()
                return dict(row) if row else None
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.get_entity error: %s", exc)
                return None
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Fact storage
    # ------------------------------------------------------------------

    def store_fact(self, key: str, value: Any) -> None:
        """
        Persist a key/value fact.  Value is JSON-encoded if not a plain string.

        Args:
            key:   Unique fact identifier (e.g. ``'user_name'``).
            value: Any JSON-serialisable value.
        """
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)

        sql = (
            "INSERT INTO facts (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at"
        )
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(sql, (key, value, self._now_iso()))
                logger.debug("MemoryBank: stored fact '%s'", key)
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.store_fact error: %s", exc)
            finally:
                conn.close()

    def get_fact(self, key: str) -> Optional[str]:
        """
        Retrieve a previously stored fact by key.

        Args:
            key: Fact identifier.

        Returns:
            The stored string value, or ``None`` if the key does not exist.
        """
        sql = "SELECT value FROM facts WHERE key = ? LIMIT 1"
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(sql, (key,)).fetchone()
                return row["value"] if row else None
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.get_fact error: %s", exc)
                return None
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_memory(self, query: str) -> List[Dict[str, Any]]:
        """
        Simple keyword search across conversations, entities, and facts.

        Matches are case-insensitive substring matches.

        Args:
            query: Search term or phrase.

        Returns:
            List of result dicts, each containing a ``source`` key
            (``'conversation'``, ``'entity'``, or ``'fact'``) alongside the
            matching row data.
        """
        pattern = f"%{query.lower()}%"
        results: List[Dict[str, Any]] = []

        conv_sql = (
            "SELECT id, timestamp, role, content, session_id "
            "FROM conversations WHERE LOWER(content) LIKE ? ORDER BY id DESC LIMIT 10"
        )
        entity_sql = (
            "SELECT id, name, type, description, updated_at "
            "FROM entities WHERE LOWER(name) LIKE ? OR LOWER(description) LIKE ? LIMIT 10"
        )
        fact_sql = (
            "SELECT id, key, value, updated_at "
            "FROM facts WHERE LOWER(key) LIKE ? OR LOWER(value) LIKE ? LIMIT 10"
        )

        with self._lock:
            conn = self._get_connection()
            try:
                for row in conn.execute(conv_sql, (pattern,)).fetchall():
                    results.append({"source": "conversation", **dict(row)})
                for row in conn.execute(entity_sql, (pattern, pattern)).fetchall():
                    results.append({"source": "entity", **dict(row)})
                for row in conn.execute(fact_sql, (pattern, pattern)).fetchall():
                    results.append({"source": "fact", **dict(row)})
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.search_memory error: %s", exc)
            finally:
                conn.close()

        logger.debug("MemoryBank: search '%s' returned %d result(s)", query, len(results))
        return results

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """
        Return row counts and other metadata about the memory database.

        Returns:
            Dict with keys ``conversations``, ``entities``, ``facts``,
            ``projects``, and ``db_path``.
        """
        queries = {
            "conversations": "SELECT COUNT(*) FROM conversations",
            "entities":      "SELECT COUNT(*) FROM entities",
            "facts":         "SELECT COUNT(*) FROM facts",
            "projects":      "SELECT COUNT(*) FROM projects",
        }
        stats: Dict[str, Any] = {"db_path": str(self._db_path)}

        with self._lock:
            conn = self._get_connection()
            try:
                for key, sql in queries.items():
                    row = conn.execute(sql).fetchone()
                    stats[key] = row[0] if row else 0
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.get_stats error: %s", exc)
            finally:
                conn.close()

        return stats

    # ------------------------------------------------------------------
    # Session utilities
    # ------------------------------------------------------------------

    @staticmethod
    def new_session_id() -> str:
        """
        Generate and return a fresh UUID4 string to identify a new chat session.

        Returns:
            UUID4 string, e.g. ``'3f2504e0-4f89-11d3-9a0c-0305e82c3301'``.
        """
        return str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Project management  (bonus CRUD surface used by other skills)
    # ------------------------------------------------------------------

    def add_project(self, name: str, description: str = "", status: str = "active") -> None:
        """
        Insert or update a project record.

        Args:
            name:        Unique project name.
            description: Optional project notes.
            status:      Lifecycle status string (default ``'active'``).
        """
        sql = (
            "INSERT INTO projects (name, status, description, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET status = excluded.status, "
            "description = excluded.description"
        )
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(sql, (name, status, description, self._now_iso()))
                logger.debug("MemoryBank: upserted project '%s'", name)
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.add_project error: %s", exc)
            finally:
                conn.close()

    def list_projects(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all projects, optionally filtered by status.

        Args:
            status: Filter by this status string, or ``None`` for all.

        Returns:
            List of project dicts.
        """
        if status:
            sql = (
                "SELECT id, name, status, description, created_at "
                "FROM projects WHERE status = ? ORDER BY id"
            )
            params = (status,)
        else:
            sql = "SELECT id, name, status, description, created_at FROM projects ORDER BY id"
            params = ()  # type: ignore[assignment]

        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.Error as exc:
                logger.exception("MemoryBank.list_projects error: %s", exc)
                return []
            finally:
                conn.close()
