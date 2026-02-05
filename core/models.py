"""
Data models and abstract base classes for the multi-function Slack bot.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


class MessageResult(Enum):
    """Result of processing a message."""
    SUCCESS = "success"
    ERROR = "error"
    NO_ACTION = "no_action"


@dataclass
class FunctionResponse:
    """Response from a function's message handler."""
    result: MessageResult
    messages: list[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FunctionInfo:
    """Metadata about a function."""
    name: str
    display_name: str
    slash_command: str
    description: str
    help_text: str
    version: str = "1.0.0"


class BotFunction(ABC):
    """
    Abstract base class that all function modules must implement.

    Each function is responsible for:
    - Providing metadata about itself
    - Handling messages routed to it
    - Providing help/welcome text
    """

    @abstractmethod
    def get_info(self) -> FunctionInfo:
        """Return metadata about this function."""
        pass

    @abstractmethod
    def handle_message(self, user_id: str, text: str, event: dict) -> FunctionResponse:
        """
        Process an incoming message.

        Args:
            user_id: Slack user ID
            text: Message text
            event: Full Slack event dict for additional context

        Returns:
            FunctionResponse with messages to send back
        """
        pass

    @abstractmethod
    def get_welcome_message(self) -> str:
        """Return welcome message shown when user switches to this function."""
        pass

    def on_activate(self, user_id: str) -> Optional[str]:
        """
        Called when a user switches to this function.
        Override to perform setup or return additional messages.
        """
        return None

    def on_deactivate(self, user_id: str) -> None:
        """
        Called when a user switches away from this function.
        Override to perform cleanup.
        """
        pass
