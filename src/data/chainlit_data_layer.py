"""
SQLite Data Layer per Chainlit - OVV ISO Chat v3.9.3

Implementa BaseDataLayer per persistenza dati:
- Thread/Conversazioni
- Feedback utente (👍👎)
- Steps e Elements
- Utenti

Database: data/persist/chainlit.db
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from chainlit.data import BaseDataLayer
from chainlit.types import (
    Feedback,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)

if TYPE_CHECKING:
    from chainlit.element import Element, ElementDict
    from chainlit.step import StepDict
    from chainlit.user import PersistedUser, User

logger = logging.getLogger(__name__)

# Singleton instance
_data_layer: Optional["SQLiteDataLayer"] = None


def get_data_layer() -> "SQLiteDataLayer":
    """Get or create SQLite data layer singleton"""
    global _data_layer
    if _data_layer is None:
        _data_layer = SQLiteDataLayer()
    return _data_layer


class SQLiteDataLayer(BaseDataLayer):
    """
    SQLite-based data layer per Chainlit.
    
    Salva tutti i dati in un database SQLite locale:
    - Threads (conversazioni)
    - Steps (messaggi/azioni)
    - Elements (file, immagini)
    - Feedbacks (👍👎)
    - Users
    """
    
    def __init__(self, db_path: str = "data/persist/chainlit.db"):
        """
        Inizializza il data layer.
        
        Args:
            db_path: Path al database SQLite
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"[DataLayer] SQLite inizializzato: {self.db_path}")
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Crea tabelle se non esistono"""
        conn = self._get_conn()
        try:
            # Users table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    identifier TEXT UNIQUE NOT NULL,
                    display_name TEXT,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            
            # Threads table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    user_id TEXT,
                    metadata TEXT DEFAULT '{}',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)
            
            # Steps table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS steps (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    parent_id TEXT,
                    name TEXT,
                    type TEXT,
                    input TEXT,
                    output TEXT,
                    metadata TEXT DEFAULT '{}',
                    start_time TEXT,
                    end_time TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES threads(id)
                )
            """)
            
            # Elements table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS elements (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT,
                    step_id TEXT,
                    type TEXT,
                    name TEXT,
                    display TEXT,
                    mime TEXT,
                    url TEXT,
                    path TEXT,
                    size INTEGER,
                    content TEXT,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES threads(id)
                )
            """)
            
            # Feedbacks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedbacks (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT,
                    for_id TEXT NOT NULL,
                    value INTEGER NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES threads(id)
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_steps_thread ON steps(thread_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_elements_thread ON elements(thread_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedbacks_thread ON feedbacks(thread_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedbacks_for ON feedbacks(for_id)")
            
            conn.commit()
            logger.debug("[DataLayer] Database tables created/verified")
        finally:
            conn.close()
    
    # =========================================================================
    # USER METHODS
    # =========================================================================
    
    async def get_user(self, identifier: str) -> Optional["PersistedUser"]:
        """Get user by identifier"""
        from chainlit.user import PersistedUser
        
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE identifier = ?",
                (identifier,)
            ).fetchone()
            
            if row:
                return PersistedUser(
                    id=row["id"],
                    identifier=row["identifier"],
                    display_name=row["display_name"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                    createdAt=row["created_at"]
                )
            return None
        finally:
            conn.close()
    
    async def create_user(self, user: "User") -> Optional["PersistedUser"]:
        """Create a new user"""
        from chainlit.user import PersistedUser
        
        conn = self._get_conn()
        try:
            user_id = str(uuid.uuid4())
            created_at = datetime.utcnow().isoformat()
            
            conn.execute("""
                INSERT OR REPLACE INTO users (id, identifier, display_name, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_id,
                user.identifier,
                user.display_name,
                json.dumps(user.metadata) if user.metadata else "{}",
                created_at
            ))
            conn.commit()
            
            return PersistedUser(
                id=user_id,
                identifier=user.identifier,
                display_name=user.display_name,
                metadata=user.metadata or {},
                createdAt=created_at
            )
        finally:
            conn.close()
    
    # =========================================================================
    # FEEDBACK METHODS
    # =========================================================================
    
    async def upsert_feedback(self, feedback: Feedback) -> str:
        """Save or update feedback"""
        conn = self._get_conn()
        try:
            feedback_id = feedback.id or str(uuid.uuid4())
            created_at = datetime.utcnow().isoformat()
            
            conn.execute("""
                INSERT OR REPLACE INTO feedbacks (id, thread_id, for_id, value, comment, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                feedback_id,
                feedback.threadId,
                feedback.forId,
                feedback.value,
                feedback.comment,
                created_at
            ))
            conn.commit()
            
            logger.info(f"[DataLayer] Feedback saved: {feedback_id} (value={feedback.value})")
            return feedback_id
        finally:
            conn.close()
    
    async def delete_feedback(self, feedback_id: str) -> bool:
        """Delete feedback by ID"""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM feedbacks WHERE id = ?",
                (feedback_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    # =========================================================================
    # ELEMENT METHODS
    # =========================================================================
    
    async def create_element(self, element: "Element"):
        """Create an element"""
        conn = self._get_conn()
        try:
            created_at = datetime.utcnow().isoformat()
            
            conn.execute("""
                INSERT OR REPLACE INTO elements 
                (id, thread_id, step_id, type, name, display, mime, url, path, size, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                element.id,
                element.thread_id if hasattr(element, 'thread_id') else None,
                element.for_id if hasattr(element, 'for_id') else None,
                element.type if hasattr(element, 'type') else None,
                element.name if hasattr(element, 'name') else None,
                element.display if hasattr(element, 'display') else None,
                element.mime if hasattr(element, 'mime') else None,
                element.url if hasattr(element, 'url') else None,
                element.path if hasattr(element, 'path') else None,
                element.size if hasattr(element, 'size') else None,
                element.content if hasattr(element, 'content') else None,
                json.dumps(element.metadata) if hasattr(element, 'metadata') and element.metadata else "{}",
                created_at
            ))
            conn.commit()
            logger.debug(f"[DataLayer] Element created: {element.id}")
        finally:
            conn.close()
    
    async def get_element(
        self, thread_id: str, element_id: str
    ) -> Optional["ElementDict"]:
        """Get element by ID"""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM elements WHERE id = ? AND thread_id = ?",
                (element_id, thread_id)
            ).fetchone()
            
            if row:
                return {
                    "id": row["id"],
                    "threadId": row["thread_id"],
                    "type": row["type"],
                    "name": row["name"],
                    "display": row["display"],
                    "mime": row["mime"],
                    "url": row["url"],
                    "path": row["path"],
                    "size": row["size"],
                    "content": row["content"],
                }
            return None
        finally:
            conn.close()
    
    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        """Delete element"""
        conn = self._get_conn()
        try:
            if thread_id:
                conn.execute(
                    "DELETE FROM elements WHERE id = ? AND thread_id = ?",
                    (element_id, thread_id)
                )
            else:
                conn.execute(
                    "DELETE FROM elements WHERE id = ?",
                    (element_id,)
                )
            conn.commit()
        finally:
            conn.close()
    
    # =========================================================================
    # STEP METHODS
    # =========================================================================
    
    async def create_step(self, step_dict: "StepDict"):
        """Create a step"""
        conn = self._get_conn()
        try:
            created_at = datetime.utcnow().isoformat()
            
            conn.execute("""
                INSERT OR REPLACE INTO steps 
                (id, thread_id, parent_id, name, type, input, output, metadata, start_time, end_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                step_dict.get("id"),
                step_dict.get("threadId"),
                step_dict.get("parentId"),
                step_dict.get("name"),
                step_dict.get("type"),
                step_dict.get("input"),
                step_dict.get("output"),
                json.dumps(step_dict.get("metadata", {})),
                step_dict.get("startTime"),
                step_dict.get("endTime"),
                created_at
            ))
            conn.commit()
            logger.debug(f"[DataLayer] Step created: {step_dict.get('id')}")
        finally:
            conn.close()
    
    async def update_step(self, step_dict: "StepDict"):
        """Update a step"""
        conn = self._get_conn()
        try:
            conn.execute("""
                UPDATE steps SET
                    name = COALESCE(?, name),
                    type = COALESCE(?, type),
                    input = COALESCE(?, input),
                    output = COALESCE(?, output),
                    metadata = COALESCE(?, metadata),
                    end_time = COALESCE(?, end_time)
                WHERE id = ?
            """, (
                step_dict.get("name"),
                step_dict.get("type"),
                step_dict.get("input"),
                step_dict.get("output"),
                json.dumps(step_dict.get("metadata", {})) if step_dict.get("metadata") else None,
                step_dict.get("endTime"),
                step_dict.get("id")
            ))
            conn.commit()
        finally:
            conn.close()
    
    async def delete_step(self, step_id: str):
        """Delete a step"""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM steps WHERE id = ?", (step_id,))
            conn.commit()
        finally:
            conn.close()
    
    # =========================================================================
    # THREAD METHODS
    # =========================================================================
    
    async def get_thread_author(self, thread_id: str) -> str:
        """Get thread author user ID"""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT user_id FROM threads WHERE id = ?",
                (thread_id,)
            ).fetchone()
            return row["user_id"] if row and row["user_id"] else ""
        finally:
            conn.close()
    
    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        """Get thread by ID"""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM threads WHERE id = ?",
                (thread_id,)
            ).fetchone()
            
            if not row:
                return None
            
            # Get steps for this thread
            steps_rows = conn.execute(
                "SELECT * FROM steps WHERE thread_id = ? ORDER BY created_at",
                (thread_id,)
            ).fetchall()
            
            steps = []
            for s in steps_rows:
                steps.append({
                    "id": s["id"],
                    "threadId": s["thread_id"],
                    "parentId": s["parent_id"],
                    "name": s["name"],
                    "type": s["type"],
                    "input": s["input"],
                    "output": s["output"],
                    "metadata": json.loads(s["metadata"]) if s["metadata"] else {},
                    "startTime": s["start_time"],
                    "endTime": s["end_time"],
                })
            
            # Get elements
            elements_rows = conn.execute(
                "SELECT * FROM elements WHERE thread_id = ?",
                (thread_id,)
            ).fetchall()
            
            elements = []
            for e in elements_rows:
                elements.append({
                    "id": e["id"],
                    "threadId": e["thread_id"],
                    "type": e["type"],
                    "name": e["name"],
                    "display": e["display"],
                    "mime": e["mime"],
                    "url": e["url"],
                })
            
            return {
                "id": row["id"],
                "name": row["name"],
                "userId": row["user_id"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "createdAt": row["created_at"],
                "steps": steps,
                "elements": elements,
            }
        finally:
            conn.close()
    
    async def delete_thread(self, thread_id: str):
        """Delete thread and all related data"""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM feedbacks WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM elements WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM steps WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
            conn.commit()
            logger.info(f"[DataLayer] Thread deleted: {thread_id}")
        finally:
            conn.close()
    
    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        """List threads with pagination and filters"""
        conn = self._get_conn()
        try:
            # Build query
            query = "SELECT * FROM threads WHERE 1=1"
            params = []
            
            if filters.userId:
                query += " AND user_id = ?"
                params.append(filters.userId)
            
            if filters.search:
                query += " AND name LIKE ?"
                params.append(f"%{filters.search}%")
            
            # Count total
            count_query = query.replace("SELECT *", "SELECT COUNT(*)")
            total = conn.execute(count_query, params).fetchone()[0]
            
            # Add pagination
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            limit = pagination.first or 10
            offset = 0
            if pagination.cursor:
                # Cursor is the offset encoded
                try:
                    offset = int(pagination.cursor)
                except ValueError:
                    offset = 0
            
            params.extend([limit, offset])
            
            rows = conn.execute(query, params).fetchall()
            
            threads = []
            for row in rows:
                threads.append({
                    "id": row["id"],
                    "name": row["name"],
                    "userId": row["user_id"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "tags": json.loads(row["tags"]) if row["tags"] else [],
                    "createdAt": row["created_at"],
                    "steps": [],
                    "elements": [],
                })
            
            # Calculate next cursor
            has_more = offset + len(threads) < total
            next_cursor = str(offset + limit) if has_more else None
            
            return PaginatedResponse(
                data=threads,
                pageInfo={
                    "hasNextPage": has_more,
                    "endCursor": next_cursor,
                }
            )
        finally:
            conn.close()
    
    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        """Update thread"""
        conn = self._get_conn()
        try:
            # Check if thread exists, if not create it
            existing = conn.execute(
                "SELECT id FROM threads WHERE id = ?",
                (thread_id,)
            ).fetchone()
            
            now = datetime.utcnow().isoformat()
            
            if not existing:
                # Create new thread
                conn.execute("""
                    INSERT INTO threads (id, name, user_id, metadata, tags, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    thread_id,
                    name,
                    user_id,
                    json.dumps(metadata) if metadata else "{}",
                    json.dumps(tags) if tags else "[]",
                    now,
                    now
                ))
            else:
                # Update existing
                updates = []
                params = []
                
                if name is not None:
                    updates.append("name = ?")
                    params.append(name)
                if user_id is not None:
                    updates.append("user_id = ?")
                    params.append(user_id)
                if metadata is not None:
                    updates.append("metadata = ?")
                    params.append(json.dumps(metadata))
                if tags is not None:
                    updates.append("tags = ?")
                    params.append(json.dumps(tags))
                
                updates.append("updated_at = ?")
                params.append(now)
                params.append(thread_id)
                
                if updates:
                    query = f"UPDATE threads SET {', '.join(updates)} WHERE id = ?"
                    conn.execute(query, params)
            
            conn.commit()
        finally:
            conn.close()
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def build_debug_url(self) -> str:
        """Build URL for debugging (not applicable for SQLite)"""
        return f"sqlite://{self.db_path}"
    
    async def close(self) -> None:
        """Close data layer (cleanup)"""
        logger.info("[DataLayer] Closed")
    
    # =========================================================================
    # ANALYTICS METHODS (custom per OVV)
    # =========================================================================
    
    def get_feedback_stats(self) -> Dict:
        """Get feedback statistics"""
        conn = self._get_conn()
        try:
            stats = {
                "total": 0,
                "positive": 0,
                "negative": 0,
                "with_comments": 0,
            }
            
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN value = 1 THEN 1 ELSE 0 END) as positive,
                    SUM(CASE WHEN value = 0 THEN 1 ELSE 0 END) as negative,
                    SUM(CASE WHEN comment IS NOT NULL AND comment != '' THEN 1 ELSE 0 END) as with_comments
                FROM feedbacks
            """).fetchone()
            
            if row:
                stats["total"] = row["total"] or 0
                stats["positive"] = row["positive"] or 0
                stats["negative"] = row["negative"] or 0
                stats["with_comments"] = row["with_comments"] or 0
            
            return stats
        finally:
            conn.close()
    
    def get_recent_feedbacks(self, limit: int = 10) -> List[Dict]:
        """Get recent feedbacks"""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT f.*, s.output as message_content
                FROM feedbacks f
                LEFT JOIN steps s ON f.for_id = s.id
                ORDER BY f.created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            
            return [
                {
                    "id": row["id"],
                    "thread_id": row["thread_id"],
                    "for_id": row["for_id"],
                    "value": row["value"],
                    "comment": row["comment"],
                    "created_at": row["created_at"],
                    "message_preview": (row["message_content"] or "")[:100] if row["message_content"] else None
                }
                for row in rows
            ]
        finally:
            conn.close()

