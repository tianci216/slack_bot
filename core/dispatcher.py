"""
Central message dispatcher for the multi-function Slack bot.

Handles:
- Routing DMs to the user's current function
- Default behavior for users without a function selected
- Error handling and logging
"""

import logging
from typing import Optional, Callable

from .models import BotFunction, FunctionResponse, MessageResult
from .storage import StateStorage, PermissionsStorage, UsageLogger
from .plugin_loader import PluginLoader

logger = logging.getLogger(__name__)


class Dispatcher:
    """Central dispatcher that routes messages to the appropriate function."""

    def __init__(self):
        self.state_storage = StateStorage()
        self.permissions = PermissionsStorage()
        self.usage_logger = UsageLogger()
        self.plugin_loader = PluginLoader()
        self.functions: dict[str, BotFunction] = {}

        self._load_functions()

    def _load_functions(self) -> None:
        """Discover and load all function modules."""
        self.functions = self.plugin_loader.load_all_functions()
        logger.info(
            f"Loaded {len(self.functions)} functions: {list(self.functions.keys())}"
        )

    def get_function(self, name: str) -> Optional[BotFunction]:
        """Get a function by name."""
        return self.functions.get(name)

    def get_all_function_names(self) -> list[str]:
        """Get list of all loaded function names."""
        return list(self.functions.keys())

    def handle_dm(
        self,
        user_id: str,
        text: str,
        event: dict,
        say: Callable[[str], None]
    ) -> None:
        """
        Handle an incoming DM message.

        Args:
            user_id: Slack user ID
            text: Message text
            event: Full Slack event
            say: Slack say function for responses
        """
        current_func_name = self.state_storage.get_current_function(user_id)

        # If no function selected, show help
        if current_func_name is None:
            self._handle_no_function(user_id, say)
            return

        # Get the function
        func = self.get_function(current_func_name)
        if func is None:
            logger.error(
                f"Function '{current_func_name}' not found for user {user_id}"
            )
            self._handle_function_not_found(user_id, current_func_name, say)
            return

        # Verify permissions (in case they were revoked)
        if not self.permissions.is_user_allowed(user_id, current_func_name):
            self._handle_unauthorized(user_id, current_func_name, say)
            return

        # Route to the function
        try:
            response = func.handle_message(user_id, text, event)

            # Log the message
            self.usage_logger.log_message(
                user_id,
                current_func_name,
                text[:100] if text else None,
                response.metadata
            )

            # Update last active
            self.state_storage.update_last_active(user_id)

            self._send_response(response, say)

        except Exception as e:
            logger.exception(f"Error in function '{current_func_name}'")
            self.usage_logger.log_error(user_id, current_func_name, str(e))
            say(
                f"An error occurred: {str(e)}\n\n"
                "Please try again or contact an administrator."
            )

    def switch_user_function(
        self,
        user_id: str,
        function_name: str,
        say: Callable[[str], None]
    ) -> bool:
        """
        Switch a user to a different function.

        Args:
            user_id: Slack user ID
            function_name: Name of function to switch to
            say: Slack say function

        Returns:
            True if switch successful, False otherwise
        """
        # Check if function exists
        func = self.get_function(function_name)
        if func is None:
            say(f"Function `{function_name}` not found.")
            return False

        # Check permissions
        if not self.permissions.is_user_allowed(user_id, function_name):
            self._handle_unauthorized(user_id, function_name, say)
            return False

        # Deactivate current function
        current_func_name = self.state_storage.get_current_function(user_id)
        if current_func_name:
            current_func = self.get_function(current_func_name)
            if current_func:
                current_func.on_deactivate(user_id)

        # Update state
        self.state_storage.set_user_function(user_id, function_name)

        # Log the switch
        self.usage_logger.log_switch(user_id, current_func_name, function_name)

        # Activate new function
        activation_msg = func.on_activate(user_id)

        # Send welcome message
        say(func.get_welcome_message())
        if activation_msg:
            say(activation_msg)

        logger.info(f"User {user_id} switched to function '{function_name}'")
        return True

    def get_available_functions_for_user(self, user_id: str) -> list[BotFunction]:
        """Get list of functions available to a user."""
        all_names = self.get_all_function_names()
        allowed_names = self.permissions.get_allowed_functions(user_id, all_names)
        return [
            self.functions[name]
            for name in allowed_names
            if name in self.functions
        ]

    def _handle_no_function(
        self,
        user_id: str,
        say: Callable[[str], None]
    ) -> None:
        """Handle case where user hasn't selected a function."""
        all_names = self.get_all_function_names()
        allowed = self.permissions.get_allowed_functions(user_id, all_names)

        if not allowed:
            say(
                "You don't have access to any functions.\n"
                "Please contact an administrator."
            )
            return

        # Build function list with commands
        func_list = []
        for func_name in allowed:
            func = self.get_function(func_name)
            if func:
                info = func.get_info()
                func_list.append(f"- `{info.slash_command}` - {info.description}")

        say(
            "Welcome! You haven't selected a function yet.\n\n"
            "*Available functions:*\n" +
            "\n".join(func_list) +
            "\n\nUse a slash command to get started."
        )

    def _handle_unauthorized(
        self,
        user_id: str,
        function_name: str,
        say: Callable[[str], None]
    ) -> None:
        """Handle unauthorized access attempt."""
        logger.warning(
            f"Unauthorized access attempt: user {user_id} -> {function_name}"
        )

        # Clear the user's current function if they lost access
        self.state_storage.clear_user_function(user_id)

        say(
            f"You don't have access to `{function_name}`.\n"
            "Please contact an administrator if you need access."
        )

    def _handle_function_not_found(
        self,
        user_id: str,
        function_name: str,
        say: Callable[[str], None]
    ) -> None:
        """Handle case where user's selected function no longer exists."""
        self.state_storage.clear_user_function(user_id)

        say(
            f"The function `{function_name}` is no longer available.\n"
            "Your selection has been cleared. Please choose a new function."
        )
        self._handle_no_function(user_id, say)

    def _send_response(
        self,
        response: FunctionResponse,
        say: Callable[[str], None]
    ) -> None:
        """Send function response messages to Slack."""
        for message in response.messages:
            say(message)
