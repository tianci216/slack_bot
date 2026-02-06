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
    Platform, build_query, format_skill_picker, get_platform_note
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
ADD_PATTERN = re.compile(r"^add\s+(.+)$", re.IGNORECASE)
REMOVE_PATTERN = re.compile(r"^remove\s+(.+)$", re.IGNORECASE)

# Minimum length to consider as a job description
MIN_JD_LENGTH = 50


class BooleanSearchFunction(BotFunction):
    """
    Boolean Search Generator function.

    Parses job descriptions and generates platform-specific Boolean search queries.
    Users start with a broad query (titles + primary skill) and add skills
    incrementally from a numbered picker.
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
                "Paste a job description and I'll generate a broad starting query "
                "with a list of skills you can add.\n\n"
                "*Supported Platforms:*\n"
                "- *SeekOut* (default) - Full syntax with field operators\n"
                "- *LinkedIn* - Basic syntax without field operators\n\n"
                "*Commands:*\n"
                "- Paste a job description to generate a query\n"
                "- `add 2,5` - Add skills by number\n"
                "- `add all` - Add all skills\n"
                "- `remove 2` - Remove a skill by number\n"
                "- `platform seekout` or `platform linkedin` - Switch platform\n"
                "- `clear` - Start over with a new job description\n"
                "- `help` - Show this message\n\n"
                "*Tips:*\n"
                "- Start broad and add skills one at a time\n"
                "- Each skill you add narrows the search\n"
                "- Switch between platforms anytime"
            ),
            version="2.0.0"
        )

    def handle_message(self, user_id: str, text: str, event: dict) -> FunctionResponse:
        """Process an incoming message."""
        text = text.strip()

        if HELP_PATTERN.match(text):
            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=[self.get_info().help_text]
            )

        if CLEAR_PATTERN.match(text):
            return self._handle_clear(user_id)

        platform_match = PLATFORM_PATTERN.match(text)
        if platform_match:
            return self._handle_platform_switch(user_id, platform_match.group(1))

        add_match = ADD_PATTERN.match(text)
        if add_match:
            return self._handle_add(user_id, add_match.group(1))

        remove_match = REMOVE_PATTERN.match(text)
        if remove_match:
            return self._handle_remove(user_id, remove_match.group(1))

        # If text is long enough, treat as job description
        if len(text) >= MIN_JD_LENGTH:
            return self._handle_job_description(user_id, text)

        # Short text with active session → try as free-text refinement via LLM
        if self.conversation.has_active_session(user_id):
            return self._handle_refinement(user_id, text)

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
            "Paste a job description and I'll generate a broad starting query "
            "with a list of skills you can add.\n\n"
            "Type `help` for commands and tips."
        )

    def on_activate(self, user_id: str) -> Optional[str]:
        state = self.conversation.get_state(user_id)
        if state and state.parsed_jd:
            return (
                f"Welcome back! You have an active session for "
                f"*{state.platform.value.title()}*.\n\n"
                "Use `add`/`remove` to adjust skills, or type `clear` to start fresh."
            )
        return None

    def on_deactivate(self, user_id: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_job_description(self, user_id: str, text: str) -> FunctionResponse:
        """Parse a job description and show broad initial query + skill picker."""
        try:
            parsed_jd = parse_job_description(text)

            state = self.conversation.get_state(user_id)
            platform = state.platform if state else self.default_platform

            # Auto-select the primary skill for the initial query
            selected = []
            if parsed_jd.primary_skill and parsed_jd.primary_skill in parsed_jd.skills:
                selected = [parsed_jd.primary_skill]
            elif parsed_jd.skills:
                selected = [parsed_jd.skills[0]]

            query = build_query(parsed_jd, platform, selected)

            new_state = ConversationState(
                user_id=user_id,
                platform=platform,
                parsed_jd=parsed_jd,
                current_query=query,
                original_text=text[:1000],
                last_updated=datetime.utcnow(),
                selected_skills=selected,
            )
            self.conversation.set_state(new_state)

            display = format_skill_picker(query, platform, parsed_jd, selected)
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
                    "skills_count": len(parsed_jd.skills),
                }
            )

        except RateLimitError:
            return FunctionResponse(
                result=MessageResult.ERROR,
                messages=["API rate limit reached. Please try again in a minute."],
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
                messages=["An unexpected error occurred. Please try again."],
                error=f"Unexpected error: {e}"
            )

    def _handle_add(self, user_id: str, arg: str) -> FunctionResponse:
        """Add skills to the query by number, name, or 'all'."""
        state = self.conversation.get_state(user_id)
        if not state or not state.parsed_jd:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=["No active search. Please paste a job description first."]
            )

        skills_list = state.parsed_jd.skills
        selected = list(state.selected_skills)
        added = []

        if arg.strip().lower() == "all":
            for skill in skills_list:
                if skill not in selected:
                    selected.append(skill)
                    added.append(skill)
        else:
            # Try parsing as comma/space-separated numbers
            tokens = re.split(r"[,\s]+", arg.strip())
            parsed_any_number = False
            for token in tokens:
                try:
                    idx = int(token)
                    if 1 <= idx <= len(skills_list):
                        skill = skills_list[idx - 1]
                        if skill not in selected:
                            selected.append(skill)
                            added.append(skill)
                        parsed_any_number = True
                except ValueError:
                    continue

            # If no numbers parsed, try matching the whole arg as a skill name
            if not parsed_any_number:
                skill_name = arg.strip()
                # Case-insensitive match against available skills
                match = next(
                    (s for s in skills_list if s.lower() == skill_name.lower()),
                    None
                )
                if match:
                    if match not in selected:
                        selected.append(match)
                        added.append(match)
                else:
                    return FunctionResponse(
                        result=MessageResult.NO_ACTION,
                        messages=[
                            f"Skill not found: `{skill_name}`\n"
                            "Use a number from the list or the exact skill name."
                        ]
                    )

        if not added:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=["Those skills are already in your query."]
            )

        return self._rebuild_and_respond(state, selected)

    def _handle_remove(self, user_id: str, arg: str) -> FunctionResponse:
        """Remove skills from the query by number or name."""
        state = self.conversation.get_state(user_id)
        if not state or not state.parsed_jd:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=["No active search. Please paste a job description first."]
            )

        skills_list = state.parsed_jd.skills
        selected = list(state.selected_skills)
        removed = []

        if arg.strip().lower() == "all":
            removed = list(selected)
            selected = []
        else:
            tokens = re.split(r"[,\s]+", arg.strip())
            parsed_any_number = False
            for token in tokens:
                try:
                    idx = int(token)
                    if 1 <= idx <= len(skills_list):
                        skill = skills_list[idx - 1]
                        if skill in selected:
                            selected.remove(skill)
                            removed.append(skill)
                        parsed_any_number = True
                except ValueError:
                    continue

            if not parsed_any_number:
                skill_name = arg.strip()
                match = next(
                    (s for s in selected if s.lower() == skill_name.lower()),
                    None
                )
                if match:
                    selected.remove(match)
                    removed.append(match)
                else:
                    return FunctionResponse(
                        result=MessageResult.NO_ACTION,
                        messages=[
                            f"Skill not in your query: `{skill_name}`"
                        ]
                    )

        if not removed:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=["Those skills aren't in your query."]
            )

        return self._rebuild_and_respond(state, selected)

    def _rebuild_and_respond(
        self, state: ConversationState, selected: list[str]
    ) -> FunctionResponse:
        """Rebuild query with new selected skills and return the skill picker."""
        query = build_query(state.parsed_jd, state.platform, selected)

        state.selected_skills = selected
        state.current_query = query
        state.last_updated = datetime.utcnow()
        self.conversation.set_state(state)

        display = format_skill_picker(
            query, state.platform, state.parsed_jd, selected
        )
        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=[display],
            metadata={"selected_count": len(selected)}
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
            state.platform = platform
            return self._rebuild_and_respond(state, state.selected_skills)
        else:
            new_state = ConversationState(
                user_id=user_id,
                platform=platform,
                parsed_jd=None,
                current_query=None,
                original_text=None,
                last_updated=datetime.utcnow(),
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
        """Apply a free-text refinement to the extracted data via LLM."""
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
            updated_jd = apply_refinement(state.parsed_jd, instruction)
            state.parsed_jd = updated_jd
            # Keep selected skills that still exist in the updated skills list
            state.selected_skills = [
                s for s in state.selected_skills if s in updated_jd.skills
            ]
            return self._rebuild_and_respond(state, state.selected_skills)

        except (LLMError, ParseError) as e:
            logger.exception("Error applying refinement")
            return FunctionResponse(
                result=MessageResult.ERROR,
                messages=[
                    f"Couldn't apply that change: {e}\n"
                    "Try `add 1,3` or `remove 2` instead."
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
