"""
Plugin loader for dynamically loading function modules.
"""

import importlib.util
import logging
from pathlib import Path
from typing import Optional

from .models import BotFunction

logger = logging.getLogger(__name__)

BOT_ROOT = Path(__file__).parent.parent
FUNCTIONS_DIR = BOT_ROOT / "functions"


class PluginLoader:
    """
    Discovers and loads BotFunction implementations from subdirectories.

    Each function folder must contain:
    - function.py with a get_function() factory
    """

    def __init__(self, root_dir: Path | None = None, allowed_functions: list[str] | None = None):
        self.root_dir = root_dir if root_dir is not None else FUNCTIONS_DIR
        self.allowed_functions = allowed_functions
        self.excluded_dirs = {'__pycache__', '.git', '.venv', '.tmp'}

    def discover_functions(self) -> list[str]:
        """
        Find all directories that contain a function module.

        Returns:
            List of function directory names
        """
        functions = []

        for item in self.root_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name in self.excluded_dirs or item.name.startswith('.'):
                continue
            if self.allowed_functions is not None and item.name not in self.allowed_functions:
                continue

            function_file = item / "function.py"
            if function_file.exists():
                functions.append(item.name)
                logger.debug(f"Discovered function: {item.name}")

        return functions

    def load_function(self, name: str) -> Optional[BotFunction]:
        """
        Load a single function by directory name.

        Args:
            name: Directory name of the function

        Returns:
            BotFunction instance or None if loading fails
        """
        function_path = self.root_dir / name / "function.py"

        if not function_path.exists():
            logger.error(f"Function file not found: {function_path}")
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"functions.{name}",
                function_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, 'get_function'):
                func = module.get_function()
                if isinstance(func, BotFunction):
                    return func
                else:
                    logger.error(
                        f"get_function() in {name} did not return BotFunction"
                    )
            else:
                logger.error(f"No get_function() in {name}/function.py")

        except Exception as e:
            logger.exception(f"Failed to load function '{name}': {e}")

        return None

    def load_all_functions(self) -> dict[str, BotFunction]:
        """
        Load all discovered functions.

        Returns:
            Dict mapping function names to BotFunction instances
        """
        functions = {}

        for name in self.discover_functions():
            func = self.load_function(name)
            if func:
                functions[name] = func
                info = func.get_info()
                logger.info(f"Loaded function: {name} ({info.display_name})")

        return functions
