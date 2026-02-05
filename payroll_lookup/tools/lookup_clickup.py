"""
ClickUp API Client for Payroll Link Lookup Bot

Fetches task information from ClickUp API.
"""

import os
import requests
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class ClickUpTask:
    task_name: str
    status: str
    url: str


def lookup_task(task_id: str, original_url: str) -> dict:
    """
    Look up a ClickUp task by ID.

    Args:
        task_id: The ClickUp task ID
        original_url: The original URL for reference

    Returns:
        dict with task_name, status, url on success
        dict with error, url on failure
    """
    load_dotenv()

    api_token = os.getenv("CLICKUP_API_TOKEN")
    if not api_token:
        return {"error": "CLICKUP_API_TOKEN not configured", "url": original_url}

    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(
            f"https://api.clickup.com/api/v2/task/{task_id}",
            headers=headers,
            timeout=10
        )

        if response.status_code == 401:
            return {"error": "Invalid ClickUp API token", "url": original_url}

        if response.status_code == 404:
            return {"error": "Task not found", "url": original_url}

        if response.status_code != 200:
            return {"error": f"ClickUp API error: {response.status_code}", "url": original_url}

        data = response.json()

        task_name = data.get("name", "Unknown Task")
        status = data.get("status", {}).get("status", "Unknown")

        return {
            "task_name": task_name,
            "status": status,
            "url": original_url
        }

    except requests.exceptions.Timeout:
        return {"error": "ClickUp API timeout", "url": original_url}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}", "url": original_url}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "url": original_url}


def format_response(result: dict) -> list[str]:
    """
    Format the lookup result as a list of values for Sheets.

    Returns: [task_name, status] or [error_message]
    """
    if "error" in result:
        return [f"ERROR: {result['error']}"]

    return [result['task_name'], result['status']]


# For testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python lookup_clickup.py <task_id>")
        print("Example: python lookup_clickup.py 86a1b2c3d")
        sys.exit(1)

    task_id = sys.argv[1]
    result = lookup_task(task_id, f"https://app.clickup.com/t/{task_id}")

    print("Result:")
    print(f"  {result}")
    print(f"\nFormatted: {format_response(result)}")
