"""
Storage layer for user state, permissions, and usage logging.

Uses SQLite for persistence.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
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


def init_database():
    """Initialize database with required tables."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # User state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                user_id TEXT PRIMARY KEY,
                current_function TEXT,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Function permissions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS function_permissions (
                function_name TEXT,
                user_id TEXT,
                PRIMARY KEY (function_name, user_id)
            )
        """)

        # Open functions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS open_functions (
                function_name TEXT PRIMARY KEY
            )
        """)

        # Admins table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id TEXT PRIMARY KEY
            )
        """)

        # Usage logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                function_name TEXT NOT NULL,
                action TEXT NOT NULL,
                message_preview TEXT,
                metadata TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for usage_logs
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_logs_user
            ON usage_logs(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_logs_function
            ON usage_logs(function_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_logs_timestamp
            ON usage_logs(timestamp)
        """)

    logger.info(f"Database initialized at {get_db_path()}")


class StateStorage:
    """Manages user state persistence."""

    def __init__(self):
        init_database()

    def get_current_function(self, user_id: str) -> Optional[str]:
        """Get the current function name for a user, or None."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_function FROM user_state WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return row["current_function"] if row else None

    def set_user_function(self, user_id: str, function_name: Optional[str]) -> None:
        """Set the current function for a user."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_state (user_id, current_function, last_active)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    current_function = excluded.current_function,
                    last_active = excluded.last_active
            """, (user_id, function_name, datetime.utcnow().isoformat()))

    def clear_user_function(self, user_id: str) -> None:
        """Clear the user's current function."""
        self.set_user_function(user_id, None)

    def update_last_active(self, user_id: str) -> None:
        """Update the user's last active timestamp."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_state SET last_active = ? WHERE user_id = ?
            """, (datetime.utcnow().isoformat(), user_id))


class PermissionsStorage:
    """Manages function access permissions."""

    def __init__(self):
        init_database()

    def is_user_allowed(self, user_id: str, function_name: str) -> bool:
        """Check if user is allowed to access a function."""
        with get_connection() as conn:
            cursor = conn.cursor()

            # Check if user is admin
            cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                return True

            # Check if function is open to all
            cursor.execute(
                "SELECT 1 FROM open_functions WHERE function_name = ?",
                (function_name,)
            )
            if cursor.fetchone():
                return True

            # Check function-specific permissions
            cursor.execute("""
                SELECT 1 FROM function_permissions
                WHERE function_name = ? AND user_id = ?
            """, (function_name, user_id))
            return cursor.fetchone() is not None

    def get_allowed_functions(self, user_id: str, all_functions: list[str]) -> list[str]:
        """Get list of function names the user can access."""
        with get_connection() as conn:
            cursor = conn.cursor()

            # Check if user is admin
            cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                return all_functions

            allowed = []
            for func_name in all_functions:
                # Check if function is open
                cursor.execute(
                    "SELECT 1 FROM open_functions WHERE function_name = ?",
                    (func_name,)
                )
                if cursor.fetchone():
                    allowed.append(func_name)
                    continue

                # Check specific permission
                cursor.execute("""
                    SELECT 1 FROM function_permissions
                    WHERE function_name = ? AND user_id = ?
                """, (func_name, user_id))
                if cursor.fetchone():
                    allowed.append(func_name)

            return allowed

    def add_user_to_function(self, user_id: str, function_name: str) -> None:
        """Add user to a function's allow list."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO function_permissions (function_name, user_id)
                VALUES (?, ?)
            """, (function_name, user_id))

    def remove_user_from_function(self, user_id: str, function_name: str) -> None:
        """Remove user from a function's allow list."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM function_permissions
                WHERE function_name = ? AND user_id = ?
            """, (function_name, user_id))

    def set_function_open(self, function_name: str, is_open: bool) -> None:
        """Set whether a function is open to all users."""
        with get_connection() as conn:
            cursor = conn.cursor()
            if is_open:
                cursor.execute("""
                    INSERT OR IGNORE INTO open_functions (function_name) VALUES (?)
                """, (function_name,))
            else:
                cursor.execute(
                    "DELETE FROM open_functions WHERE function_name = ?",
                    (function_name,)
                )

    def add_admin(self, user_id: str) -> None:
        """Add a user as admin."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
                (user_id,)
            )

    def remove_admin(self, user_id: str) -> None:
        """Remove a user from admins."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))

    def is_admin(self, user_id: str) -> bool:
        """Check if user is an admin."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None


class UsageLogger:
    """Logs all function usage for analytics."""

    def __init__(self):
        init_database()

    def log_message(
        self,
        user_id: str,
        function_name: str,
        message_preview: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> None:
        """Log a message sent to a function."""
        self._log(user_id, function_name, "message", message_preview, metadata)

    def log_switch(
        self,
        user_id: str,
        from_function: Optional[str],
        to_function: str
    ) -> None:
        """Log a function switch."""
        metadata = {"from": from_function, "to": to_function}
        self._log(user_id, to_function, "switch", None, metadata)

    def log_error(
        self,
        user_id: str,
        function_name: str,
        error: str
    ) -> None:
        """Log an error in a function."""
        self._log(user_id, function_name, "error", None, {"error": error})

    def _log(
        self,
        user_id: str,
        function_name: str,
        action: str,
        message_preview: Optional[str],
        metadata: Optional[dict]
    ) -> None:
        """Internal logging method."""
        # Truncate message preview
        if message_preview and len(message_preview) > 100:
            message_preview = message_preview[:100]

        metadata_json = json.dumps(metadata) if metadata else None

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usage_logs
                (user_id, function_name, action, message_preview, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, function_name, action, message_preview, metadata_json))

    def get_user_stats(self, user_id: str) -> dict:
        """Get usage statistics for a user."""
        with get_connection() as conn:
            cursor = conn.cursor()

            # Total message count
            cursor.execute("""
                SELECT COUNT(*) as count FROM usage_logs
                WHERE user_id = ? AND action = 'message'
            """, (user_id,))
            message_count = cursor.fetchone()["count"]

            # Function breakdown
            cursor.execute("""
                SELECT function_name, COUNT(*) as count FROM usage_logs
                WHERE user_id = ? AND action = 'message'
                GROUP BY function_name
            """, (user_id,))
            by_function = {row["function_name"]: row["count"] for row in cursor.fetchall()}

            # Last active
            cursor.execute("""
                SELECT MAX(timestamp) as last FROM usage_logs WHERE user_id = ?
            """, (user_id,))
            last_active = cursor.fetchone()["last"]

            return {
                "message_count": message_count,
                "by_function": by_function,
                "last_active": last_active
            }

    def get_function_stats(self, function_name: str) -> dict:
        """Get usage statistics for a function."""
        with get_connection() as conn:
            cursor = conn.cursor()

            # Total usage
            cursor.execute("""
                SELECT COUNT(*) as count FROM usage_logs
                WHERE function_name = ? AND action = 'message'
            """, (function_name,))
            message_count = cursor.fetchone()["count"]

            # Unique users
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as count FROM usage_logs
                WHERE function_name = ?
            """, (function_name,))
            unique_users = cursor.fetchone()["count"]

            # Error count
            cursor.execute("""
                SELECT COUNT(*) as count FROM usage_logs
                WHERE function_name = ? AND action = 'error'
            """, (function_name,))
            error_count = cursor.fetchone()["count"]

            return {
                "message_count": message_count,
                "unique_users": unique_users,
                "error_count": error_count
            }
