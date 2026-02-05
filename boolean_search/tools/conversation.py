"""
Conversation state management for Boolean Search function.

Persists user state (platform, parsed JD, current query) in SQLite.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
from contextlib import contextmanager

from job_parser import ParsedJobDescription
from query_builder import Platform

logger = logging.getLogger(__name__)

# Use the shared database from core
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH = DATA_DIR / "bot.db"


def get_db_path() -> Path:
    """Get the database path, creating directory if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@dataclass
class ConversationState:
    """State for a user's Boolean search conversation."""
    user_id: str
    platform: Platform
    parsed_jd: Optional[ParsedJobDescription]
    current_query: Optional[str]
    original_text: Optional[str]
    last_updated: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "platform": self.platform.value,
            "parsed_jd": self.parsed_jd.to_dict() if self.parsed_jd else None,
            "current_query": self.current_query,
            "original_text": self.original_text,
            "last_updated": self.last_updated.isoformat()
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ConversationState":
        """Create from database row."""
        parsed_jd = None
        if row["parsed_jd_json"]:
            try:
                data = json.loads(row["parsed_jd_json"])
                parsed_jd = ParsedJobDescription.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                pass

        platform = Platform.from_string(row["platform"]) or Platform.SEEKOUT

        return cls(
            user_id=row["user_id"],
            platform=platform,
            parsed_jd=parsed_jd,
            current_query=row["current_query"],
            original_text=row["original_text"],
            last_updated=datetime.fromisoformat(row["last_updated"])
        )


class ConversationManager:
    """Manages conversation state per user using SQLite."""

    def __init__(self):
        self._init_table()

    def _init_table(self):
        """Initialize the conversation state table."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS boolean_search_state (
                    user_id TEXT PRIMARY KEY,
                    platform TEXT DEFAULT 'seekout',
                    parsed_jd_json TEXT,
                    current_query TEXT,
                    original_text TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        logger.info("Boolean search state table initialized")

    def get_state(self, user_id: str) -> Optional[ConversationState]:
        """
        Retrieve user's conversation state.

        Args:
            user_id: Slack user ID

        Returns:
            ConversationState or None if no state exists
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM boolean_search_state WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return ConversationState.from_row(row)
            return None

    def set_state(self, state: ConversationState) -> None:
        """
        Persist user's conversation state.

        Args:
            state: ConversationState to save
        """
        parsed_jd_json = None
        if state.parsed_jd:
            parsed_jd_json = json.dumps(state.parsed_jd.to_dict())

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO boolean_search_state
                (user_id, platform, parsed_jd_json, current_query, original_text, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    platform = excluded.platform,
                    parsed_jd_json = excluded.parsed_jd_json,
                    current_query = excluded.current_query,
                    original_text = excluded.original_text,
                    last_updated = excluded.last_updated
            """, (
                state.user_id,
                state.platform.value,
                parsed_jd_json,
                state.current_query,
                state.original_text,
                datetime.utcnow().isoformat()
            ))

    def clear_state(self, user_id: str) -> None:
        """
        Clear user's conversation state.

        Args:
            user_id: Slack user ID
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM boolean_search_state WHERE user_id = ?",
                (user_id,)
            )
        logger.info(f"Cleared conversation state for user {user_id}")

    def update_platform(self, user_id: str, platform: Platform) -> Optional[ConversationState]:
        """
        Update the platform for a user's conversation.

        Args:
            user_id: Slack user ID
            platform: New platform

        Returns:
            Updated ConversationState or None if no state exists
        """
        state = self.get_state(user_id)
        if state:
            state.platform = platform
            state.last_updated = datetime.utcnow()
            self.set_state(state)
        return state

    def has_active_session(self, user_id: str) -> bool:
        """
        Check if user has an active session with a parsed JD.

        Args:
            user_id: Slack user ID

        Returns:
            True if user has a parsed JD in their state
        """
        state = self.get_state(user_id)
        return state is not None and state.parsed_jd is not None
