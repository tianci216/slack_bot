"""
Boolean query builder for different recruiting platforms.

Supports:
- SeekOut: Full syntax with field operators, wildcards, proximity
- LinkedIn: Basic syntax without field operators or wildcards
"""

from enum import Enum
from typing import Optional
from job_parser import ParsedJobDescription


class Platform(Enum):
    """Supported recruiting platforms."""
    SEEKOUT = "seekout"
    LINKEDIN = "linkedin"

    @classmethod
    def from_string(cls, value: str) -> Optional["Platform"]:
        """Parse platform from string, case-insensitive."""
        value = value.lower().strip()
        for platform in cls:
            if platform.value == value:
                return platform
        return None


def build_query(
    parsed_jd: ParsedJobDescription,
    platform: Platform,
    selected_skills: list[str] | None = None
) -> str:
    """
    Build a Boolean query for the specified platform using only selected skills.

    Args:
        parsed_jd: Parsed job description data
        platform: Target platform
        selected_skills: Skills to include in the query (AND'd together)

    Returns:
        Boolean query string formatted for the platform
    """
    if platform == Platform.SEEKOUT:
        return _build_seekout_query(parsed_jd, selected_skills or [])
    elif platform == Platform.LINKEDIN:
        return _build_linkedin_query(parsed_jd, selected_skills or [])
    else:
        raise ValueError(f"Unsupported platform: {platform}")


def _build_seekout_query(
    parsed_jd: ParsedJobDescription,
    selected_skills: list[str]
) -> str:
    """Build a SeekOut Boolean query with field operators."""
    parts = []

    # Job titles with field operator
    if parsed_jd.job_titles:
        titles = _format_or_group(parsed_jd.job_titles, quote=True)
        parts.append(f"cur_title:({titles})")

    # Only selected skills, AND'd together
    if selected_skills:
        skills = _format_and_group(selected_skills, quote=True)
        parts.append(f"skills:({skills})")

    # Company exclusions using minus syntax
    for company in parsed_jd.companies_to_exclude:
        parts.append(f'-cur_company:"{company}"')

    if not parts:
        return ""

    return " AND ".join(parts)


def _build_linkedin_query(
    parsed_jd: ParsedJobDescription,
    selected_skills: list[str]
) -> str:
    """Build a LinkedIn Boolean query (no field operators)."""
    parts = []

    # Job titles as OR group
    if parsed_jd.job_titles:
        titles = _format_or_group(parsed_jd.job_titles, quote=True)
        parts.append(f"({titles})")

    # Only selected skills, AND'd together
    if selected_skills:
        skills = _format_and_group(selected_skills, quote=True)
        parts.append(f"({skills})")

    # Company exclusions using NOT
    for company in parsed_jd.companies_to_exclude:
        parts.append(f'NOT "{company}"')

    if not parts:
        return ""

    return " AND ".join(parts)


def _format_or_group(items: list[str], quote: bool = True) -> str:
    """Format items as an OR group."""
    if not items:
        return ""
    if quote:
        formatted = [f'"{item}"' for item in items]
    else:
        formatted = items
    return " OR ".join(formatted)


def _format_and_group(items: list[str], quote: bool = True) -> str:
    """Format items as an AND group."""
    if not items:
        return ""
    if quote:
        formatted = [f'"{item}"' for item in items]
    else:
        formatted = items
    return " AND ".join(formatted)


def format_skill_picker(
    query: str,
    platform: Platform,
    parsed_jd: ParsedJobDescription,
    selected_skills: list[str]
) -> str:
    """
    Format the query and skill picker for display in Slack.

    Shows the current query in a code block, followed by a numbered
    list of available skills with checkmarks for selected ones.
    """
    platform_name = platform.value.title()
    selected_set = set(selected_skills)

    lines = [
        f"*Platform: {platform_name}*",
        "",
        "```",
        query,
        "```",
    ]

    # Skill picker
    if parsed_jd.skills:
        lines.append("")
        lines.append("*Available Skills:*")
        for i, skill in enumerate(parsed_jd.skills, 1):
            check = "  \u2713" if skill in selected_set else ""
            lines.append(f"`{i:>2}.` {skill}{check}")

    # Extra info
    info_parts = []
    if parsed_jd.experience_level:
        exp = parsed_jd.experience_level
        if parsed_jd.years_experience:
            exp += f" ({parsed_jd.years_experience} years)"
        info_parts.append(f"*Experience:* {exp}")
    if parsed_jd.locations:
        info_parts.append(f"*Locations:* {', '.join(parsed_jd.locations)}")
    if parsed_jd.education:
        info_parts.append(f"*Education:* {', '.join(parsed_jd.education)}")

    if info_parts:
        lines.append("")
        lines.append(" | ".join(info_parts))

    # Commands
    lines.extend([
        "",
        "*Commands:*",
        "`add 2,5` - Add skills by number",
        "`add all` - Add all skills",
        "`remove 2` - Remove a skill",
        "`platform linkedin` or `platform seekout` - Switch platform",
        "`clear` - Start over",
    ])

    return "\n".join(lines)


def get_platform_note(platform: Platform) -> str:
    """Get a note explaining platform-specific limitations."""
    if platform == Platform.LINKEDIN:
        return (
            "_Note: LinkedIn doesn't support field-based search or wildcards, "
            "so this query searches the entire profile. Results may be broader._"
        )
    return ""
