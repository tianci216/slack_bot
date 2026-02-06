"""
Conversation state management for Boolean Search function.

Persists user state (platform, parsed JD, current query) in SQLite.
"""

import sys
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

# Add parent directory for core imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.storage import get_connection
from job_parser import ParsedJobDescription
from query_builder import Platform

logger = logging.getLogger(__name__)


@dataclass
class ConversationState:
    """State for a user's Boolean search conversation."""
    user_id: str
    platform: Platform
    parsed_jd: Optional[ParsedJobDescription]
    current_query: Optional[str]
    original_text: Optional[str]
    last_updated: datetime
    selected_skills: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "platform": self.platform.value,
            "parsed_jd": self.parsed_jd.to_dict() if self.parsed_jd else None,
            "current_query": self.current_query,
            "original_text": self.original_text,
            "selected_skills": self.selected_skills,
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

        selected_skills = []
        try:
            raw = row["selected_skills_json"]
            if raw:
                selected_skills = json.loads(raw)
        except (KeyError, json.JSONDecodeError):
            pass

        return cls(
            user_id=row["user_id"],
            platform=platform,
            parsed_jd=parsed_jd,
            current_query=row["current_query"],
            original_text=row["original_text"],
            last_updated=datetime.fromisoformat(row["last_updated"]),
            selected_skills=selected_skills,
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
                    selected_skills_json TEXT DEFAULT '[]',
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Add column for existing databases
            try:
                cursor.execute(
                    "ALTER TABLE boolean_search_state "
                    "ADD COLUMN selected_skills_json TEXT DEFAULT '[]'"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
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

        selected_skills_json = json.dumps(state.selected_skills or [])

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO boolean_search_state
                (user_id, platform, parsed_jd_json, current_query, original_text,
                 selected_skills_json, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    platform = excluded.platform,
                    parsed_jd_json = excluded.parsed_jd_json,
                    current_query = excluded.current_query,
                    original_text = excluded.original_text,
                    selected_skills_json = excluded.selected_skills_json,
                    last_updated = excluded.last_updated
            """, (
                state.user_id,
                state.platform.value,
                parsed_jd_json,
                state.current_query,
                state.original_text,
                selected_skills_json,
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
