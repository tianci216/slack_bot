"""
Conversation state management for Contact Finder function.

Persists user state (search results, selections) in SQLite.
"""

import sys
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Add parent directory for core imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.storage import get_connection

logger = logging.getLogger(__name__)


class SessionMode(Enum):
    IDLE = "idle"
    AWAITING_SELECTION = "awaiting_selection"


@dataclass
class ConversationState:
    """State for a user's contact finder conversation."""
    user_id: str
    mode: SessionMode
    search_query: Optional[str] = None
    companies: list[dict] = field(default_factory=list)
    selected_indices: list[int] = field(default_factory=list)
    contacts_found: list[dict] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    current_page: int = 1

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "mode": self.mode.value,
            "search_query": self.search_query,
            "companies": self.companies,
            "selected_indices": self.selected_indices,
            "contacts_found": self.contacts_found,
            "current_page": self.current_page,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ConversationState":
        """Create from database row."""
        mode = SessionMode(row["mode"]) if row["mode"] else SessionMode.IDLE

        companies = []
        if row["companies_json"]:
            try:
                companies = json.loads(row["companies_json"])
            except json.JSONDecodeError:
                pass

        selected_indices = []
        if row["selected_indices_json"]:
            try:
                selected_indices = json.loads(row["selected_indices_json"])
            except json.JSONDecodeError:
                pass

        contacts_found = []
        if row["contacts_found_json"]:
            try:
                contacts_found = json.loads(row["contacts_found_json"])
            except json.JSONDecodeError:
                pass

        return cls(
            user_id=row["user_id"],
            mode=mode,
            search_query=row["search_query"],
            companies=companies,
            selected_indices=selected_indices,
            contacts_found=contacts_found,
            last_updated=datetime.fromisoformat(row["last_updated"]),
            current_page=row["current_page"] or 1,
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
                CREATE TABLE IF NOT EXISTS contact_finder_state (
                    user_id TEXT PRIMARY KEY,
                    mode TEXT DEFAULT 'idle',
                    search_query TEXT,
                    companies_json TEXT DEFAULT '[]',
                    selected_indices_json TEXT DEFAULT '[]',
                    contacts_found_json TEXT DEFAULT '[]',
                    current_page INTEGER DEFAULT 1,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        logger.info("Contact finder state table initialized")

    def get_state(self, user_id: str) -> Optional[ConversationState]:
        """Retrieve user's conversation state."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM contact_finder_state WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return ConversationState.from_row(row)
            return None

    def set_state(self, state: ConversationState) -> None:
        """Persist user's conversation state."""
        companies_json = json.dumps(state.companies)
        selected_indices_json = json.dumps(state.selected_indices)
        contacts_found_json = json.dumps(state.contacts_found)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO contact_finder_state
                (user_id, mode, search_query, companies_json,
                 selected_indices_json, contacts_found_json,
                 current_page, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    mode = excluded.mode,
                    search_query = excluded.search_query,
                    companies_json = excluded.companies_json,
                    selected_indices_json = excluded.selected_indices_json,
                    contacts_found_json = excluded.contacts_found_json,
                    current_page = excluded.current_page,
                    last_updated = excluded.last_updated
            """, (
                state.user_id,
                state.mode.value,
                state.search_query,
                companies_json,
                selected_indices_json,
                contacts_found_json,
                state.current_page,
                datetime.utcnow().isoformat(),
            ))

    def clear_state(self, user_id: str) -> None:
        """Clear user's conversation state."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM contact_finder_state WHERE user_id = ?",
                (user_id,)
            )
        logger.info(f"Cleared contact finder state for user {user_id}")

    def has_active_session(self, user_id: str) -> bool:
        """Check if user has an active session with search results."""
        state = self.get_state(user_id)
        return (
            state is not None
            and state.mode == SessionMode.AWAITING_SELECTION
            and len(state.companies) > 0
        )
