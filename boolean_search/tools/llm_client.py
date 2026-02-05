"""
OpenRouter API client for LLM calls.
"""

import os
import json
import time
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-3-haiku-20240307"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 2000
MAX_RETRIES = 3
RETRY_DELAY = 1.0


class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass


class RateLimitError(LLMError):
    """API rate limit exceeded."""
    pass


class ParseError(LLMError):
    """Failed to parse LLM response."""
    pass


def call_llm(
    system_prompt: str,
    user_message: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None
) -> str:
    """
    Make an API call to OpenRouter.

    Args:
        system_prompt: System instructions for the LLM
        user_message: User's input message
        model: Model ID (defaults to claude-3-haiku)
        temperature: Sampling temperature (defaults to 0.3)
        max_tokens: Maximum response tokens (defaults to 2000)

    Returns:
        The LLM's response text

    Raises:
        LLMError: If the API call fails
        RateLimitError: If rate limited
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise LLMError("OPENROUTER_API_KEY not set in environment")

    model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
    temperature = temperature if temperature is not None else float(
        os.getenv("LLM_TEMPERATURE", DEFAULT_TEMPERATURE)
    )
    max_tokens = max_tokens or int(os.getenv("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://slack-bot.local",
        "X-Title": "Boolean Search Generator"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=60
            )

            if response.status_code == 429:
                # Rate limited
                retry_after = int(response.headers.get("Retry-After", RETRY_DELAY * 2))
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Rate limited, retrying in {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                raise RateLimitError("API rate limit exceeded")

            if response.status_code != 200:
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text)
                except Exception:
                    pass
                raise LLMError(f"API error ({response.status_code}): {error_msg}")

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content

        except requests.Timeout:
            last_error = LLMError("Request timed out")
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Timeout, retrying ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)
                continue

        except requests.RequestException as e:
            last_error = LLMError(f"Request failed: {e}")
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Request error, retrying ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)
                continue

    raise last_error or LLMError("Unknown error")


def parse_json_response(response: str) -> dict:
    """
    Extract JSON from LLM response, handling markdown code blocks.

    Args:
        response: Raw LLM response text

    Returns:
        Parsed JSON as dictionary

    Raises:
        ParseError: If JSON cannot be extracted or parsed
    """
    text = response.strip()

    # Try to extract from markdown code block
    if "```" in text:
        # Find JSON code block
        start_markers = ["```json", "```"]
        for marker in start_markers:
            if marker in text:
                start = text.find(marker) + len(marker)
                end = text.find("```", start)
                if end > start:
                    text = text[start:end].strip()
                    break

    # Try to parse as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to find JSON object in text
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end])
            except json.JSONDecodeError:
                pass

        raise ParseError(f"Failed to parse JSON: {e}")
