"""
Boolean Search Generator - BotFunction Implementation

Generates Boolean search queries for recruiters based on job descriptions.
Supports SeekOut and LinkedIn platforms.
"""

import os
import sys
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

# Add tools directory to path for imports
TOOLS_DIR = Path(__file__).parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

# Add parent directory for core imports
PARENT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PARENT_DIR))

from core.models import BotFunction, FunctionInfo, FunctionResponse, MessageResult
from llm_client import LLMError, RateLimitError, ParseError
from job_parser import parse_job_description, apply_refinement, ParsedJobDescription
from query_builder import (
    Platform, build_query, format_query_display, get_platform_note
)
from conversation import ConversationManager, ConversationState

logger = logging.getLogger(__name__)

# Patterns for detecting user intents
HELP_PATTERN = re.compile(r"^help$", re.IGNORECASE)
CLEAR_PATTERN = re.compile(r"^(clear|reset|start over)$", re.IGNORECASE)
PLATFORM_PATTERN = re.compile(
    r"^(?:platform|use|switch to)\s+(seekout|linkedin)$",
    re.IGNORECASE
)
REFINEMENT_PATTERNS = [
    re.compile(r"^add\s+(.+)$", re.IGNORECASE),
    re.compile(r"^remove\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(broader|narrower|more specific|less specific)$", re.IGNORECASE),
]

# Minimum length to consider as a job description
MIN_JD_LENGTH = 50


class BooleanSearchFunction(BotFunction):
    """
    Boolean Search Generator function.

    Parses job descriptions and generates platform-specific Boolean search queries.
    """

    def __init__(self):
        # Load function-specific environment
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)

        self.conversation = ConversationManager()
        self.default_platform = Platform.from_string(
            os.getenv("DEFAULT_PLATFORM", "seekout")
        ) or Platform.SEEKOUT

    def get_info(self) -> FunctionInfo:
        return FunctionInfo(
            name="boolean_search",
            display_name="Boolean Search Generator",
            slash_command="/boolean",
            description="Generate Boolean search queries from job descriptions",
            help_text=(
                "*Boolean Search Generator Help*\n\n"
                "Paste a job description and I'll generate a Boolean search string "
                "for your recruiting platform.\n\n"
                "*Supported Platforms:*\n"
                "- *SeekOut* (default) - Full syntax with field operators\n"
                "- *LinkedIn* - Basic syntax without field operators\n\n"
                "*Commands:*\n"
                "- Paste a job description to generate a query\n"
                "- `platform seekout` or `platform linkedin` - Switch platform\n"
                "- `add [skill]` - Add a required skill\n"
                "- `remove [skill]` - Remove a skill\n"
                "- `broader` - Fewer requirements, more candidates\n"
                "- `narrower` - More specific, fewer candidates\n"
                "- `clear` - Start over with a new job description\n"
                "- `help` - Show this message\n\n"
                "*Tips:*\n"
                "- Include the full job description for best results\n"
                "- You can refine the query multiple times\n"
                "- Switch between platforms anytime"
            ),
            version="1.0.0"
        )

    def handle_message(self, user_id: str, text: str, event: dict) -> FunctionResponse:
        """
        Process an incoming message.

        Routes to appropriate handler based on message content.
        """
        text = text.strip()

        # Handle help command
        if HELP_PATTERN.match(text):
            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=[self.get_info().help_text]
            )

        # Handle clear command
        if CLEAR_PATTERN.match(text):
            return self._handle_clear(user_id)

        # Handle platform switch
        platform_match = PLATFORM_PATTERN.match(text)
        if platform_match:
            platform_str = platform_match.group(1)
            return self._handle_platform_switch(user_id, platform_str)

        # Handle refinement commands
        for pattern in REFINEMENT_PATTERNS:
            match = pattern.match(text)
            if match:
                return self._handle_refinement(user_id, text)

        # If text is long enough, treat as job description
        if len(text) >= MIN_JD_LENGTH:
            return self._handle_job_description(user_id, text)

        # Check if user has an active session and this might be a short refinement
        if self.conversation.has_active_session(user_id):
            # Try to interpret as refinement
            return self._handle_refinement(user_id, text)

        # No active session and text too short
        return FunctionResponse(
            result=MessageResult.NO_ACTION,
            messages=[
                "Please paste a job description (at least 50 characters) "
                "and I'll generate a Boolean search string.\n\n"
                "Type `help` for more information."
            ]
        )

    def get_welcome_message(self) -> str:
        return (
            "You're now using *Boolean Search Generator*.\n\n"
            "Paste a job description and I'll generate a Boolean search string "
            "for SeekOut or LinkedIn.\n\n"
            "Type `help` for commands and tips."
        )

    def on_activate(self, user_id: str) -> Optional[str]:
        """Called when user switches to this function."""
        # Check if they have an existing session
        state = self.conversation.get_state(user_id)
        if state and state.parsed_jd:
            return (
                f"Welcome back! You have an active session with a query for "
                f"*{state.platform.value.title()}*.\n\n"
                "You can refine it, switch platforms, or type `clear` to start fresh."
            )
        return None

    def on_deactivate(self, user_id: str) -> None:
        """Called when user switches away from this function."""
        # Keep state for when they return
        pass

    def _handle_job_description(self, user_id: str, text: str) -> FunctionResponse:
        """Parse a job description and generate Boolean query."""
        try:
            # Parse the job description
            parsed_jd = parse_job_description(text)

            # Get user's preferred platform or default
            state = self.conversation.get_state(user_id)
            platform = state.platform if state else self.default_platform

            # Build the query
            query = build_query(parsed_jd, platform)

            # Save state
            new_state = ConversationState(
                user_id=user_id,
                platform=platform,
                parsed_jd=parsed_jd,
                current_query=query,
                original_text=text[:1000],  # Store truncated original
                last_updated=datetime.utcnow()
            )
            self.conversation.set_state(new_state)

            # Format response
            display = format_query_display(query, platform, parsed_jd)
            platform_note = get_platform_note(platform)

            messages = [display]
            if platform_note:
                messages.append(platform_note)

            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=messages,
                metadata={
                    "platform": platform.value,
                    "titles_count": len(parsed_jd.job_titles),
                    "skills_count": len(parsed_jd.required_skills)
                }
            )

        except RateLimitError:
            return FunctionResponse(
                result=MessageResult.ERROR,
                messages=[
                    "API rate limit reached. Please try again in a minute."
                ],
                error="OpenRouter rate limit"
            )

        except ParseError as e:
            return FunctionResponse(
                result=MessageResult.ERROR,
                messages=[str(e)],
                error=f"Parse error: {e}"
            )

        except LLMError as e:
            logger.exception("LLM error processing job description")
            return FunctionResponse(
                result=MessageResult.ERROR,
                messages=[
                    "Sorry, I had trouble processing that job description. "
                    "Please try again or simplify the text."
                ],
                error=f"LLM error: {e}"
            )

        except Exception as e:
            logger.exception("Unexpected error processing job description")
            return FunctionResponse(
                result=MessageResult.ERROR,
                messages=[
                    "An unexpected error occurred. Please try again."
                ],
                error=f"Unexpected error: {e}"
            )

    def _handle_platform_switch(self, user_id: str, platform_str: str) -> FunctionResponse:
        """Switch the user's platform preference."""
        platform = Platform.from_string(platform_str)
        if not platform:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=[
                    f"Unknown platform: {platform_str}\n"
                    "Supported platforms: `seekout`, `linkedin`"
                ]
            )

        state = self.conversation.get_state(user_id)

        if state and state.parsed_jd:
            # Regenerate query for new platform
            query = build_query(state.parsed_jd, platform)
            state.platform = platform
            state.current_query = query
            state.last_updated = datetime.utcnow()
            self.conversation.set_state(state)

            display = format_query_display(query, platform, state.parsed_jd)
            platform_note = get_platform_note(platform)

            messages = [f"Switched to *{platform.value.title()}* format:\n\n{display}"]
            if platform_note:
                messages.append(platform_note)

            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=messages,
                metadata={"platform": platform.value}
            )
        else:
            # No active session, just save preference
            new_state = ConversationState(
                user_id=user_id,
                platform=platform,
                parsed_jd=None,
                current_query=None,
                original_text=None,
                last_updated=datetime.utcnow()
            )
            self.conversation.set_state(new_state)

            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=[
                    f"Platform set to *{platform.value.title()}*.\n\n"
                    "Paste a job description to generate a Boolean search."
                ]
            )

    def _handle_refinement(self, user_id: str, instruction: str) -> FunctionResponse:
        """Apply a refinement to the current query."""
        state = self.conversation.get_state(user_id)

        if not state or not state.parsed_jd:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=[
                    "No active search to refine. "
                    "Please paste a job description first."
                ]
            )

        try:
            # Apply refinement using LLM
            updated_jd = apply_refinement(state.parsed_jd, instruction)

            # Rebuild query
            query = build_query(updated_jd, state.platform)

            # Update state
            state.parsed_jd = updated_jd
            state.current_query = query
            state.last_updated = datetime.utcnow()
            self.conversation.set_state(state)

            # Format response
            display = format_query_display(query, state.platform, updated_jd)

            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=[f"Updated query:\n\n{display}"],
                metadata={"refinement": instruction}
            )

        except (LLMError, ParseError) as e:
            logger.exception("Error applying refinement")
            return FunctionResponse(
                result=MessageResult.ERROR,
                messages=[
                    f"Couldn't apply that change: {e}\n"
                    "Try a simpler instruction like `add Python` or `remove AWS`."
                ],
                error=f"Refinement error: {e}"
            )

    def _handle_clear(self, user_id: str) -> FunctionResponse:
        """Clear the user's conversation state."""
        self.conversation.clear_state(user_id)

        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=[
                "Session cleared. Paste a new job description to start fresh."
            ]
        )


def get_function() -> BotFunction:
    """Factory function called by plugin loader."""
    return BooleanSearchFunction()
