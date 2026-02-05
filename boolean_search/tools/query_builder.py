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


def build_query(parsed_jd: ParsedJobDescription, platform: Platform) -> str:
    """
    Build a Boolean query for the specified platform.

    Args:
        parsed_jd: Parsed job description data
        platform: Target platform

    Returns:
        Boolean query string formatted for the platform
    """
    if platform == Platform.SEEKOUT:
        return build_seekout_query(parsed_jd)
    elif platform == Platform.LINKEDIN:
        return build_linkedin_query(parsed_jd)
    else:
        raise ValueError(f"Unsupported platform: {platform}")


def build_seekout_query(parsed_jd: ParsedJobDescription) -> str:
    """
    Build a SeekOut Boolean query with field operators.

    SeekOut supports:
    - Field operators: cur_title:, skills:, cur_company:, etc.
    - Wildcards: java* matches javascript, javabeans
    - Proximity: "senior engineer"~1
    - AND, OR, NOT operators (uppercase)
    - Grouping with parentheses
    - Exact phrases with quotes
    - Minus symbol for exclusion: -cur_company:"Competitor"
    """
    parts = []

    # Job titles with field operator
    if parsed_jd.job_titles:
        titles = _format_or_group(parsed_jd.job_titles, quote=True)
        parts.append(f"cur_title:({titles})")

    # Required skills - use AND to require all
    if parsed_jd.required_skills:
        required = _format_and_group(parsed_jd.required_skills, quote=True)
        parts.append(f"skills:({required})")

    # Preferred skills - use OR as optional boost
    if parsed_jd.preferred_skills:
        preferred = _format_or_group(parsed_jd.preferred_skills, quote=True)
        parts.append(f"skills:({preferred})")

    # Locations
    if parsed_jd.locations:
        # Filter out "Remote" for location fields
        cities_states = [loc for loc in parsed_jd.locations if loc.lower() != "remote"]
        if cities_states:
            loc_query = _format_or_group(cities_states, quote=False)
            parts.append(f"(city:({loc_query}) OR state:({loc_query}))")

    # Education
    if parsed_jd.education:
        degrees = _format_or_group(parsed_jd.education, quote=True)
        parts.append(f"degrees:({degrees})")

    # Certifications - search in summary/skills
    if parsed_jd.certifications:
        certs = _format_or_group(parsed_jd.certifications, quote=True)
        parts.append(f"(summary:({certs}) OR skills:({certs}))")

    # Industry targeting
    if parsed_jd.industries:
        industries = _format_or_group(parsed_jd.industries, quote=True)
        parts.append(f"industry:({industries})")

    # Company exclusions using minus syntax
    for company in parsed_jd.companies_to_exclude:
        parts.append(f'-cur_company:"{company}"')

    # Join all parts with AND
    if not parts:
        return ""

    return " AND ".join(parts)


def build_linkedin_query(parsed_jd: ParsedJobDescription) -> str:
    """
    Build a LinkedIn Boolean query.

    LinkedIn supports:
    - AND, OR, NOT operators (uppercase)
    - Grouping with parentheses
    - Exact phrases with quotes
    - NO field operators (searches entire profile)
    - NO wildcards
    """
    parts = []

    # Job titles as OR group
    if parsed_jd.job_titles:
        titles = _format_or_group(parsed_jd.job_titles, quote=True)
        parts.append(f"({titles})")

    # Required skills as AND group
    if parsed_jd.required_skills:
        required = _format_and_group(parsed_jd.required_skills, quote=True)
        parts.append(f"({required})")

    # Preferred skills as OR group (weaker matching)
    if parsed_jd.preferred_skills:
        preferred = _format_or_group(parsed_jd.preferred_skills, quote=True)
        parts.append(f"({preferred})")

    # Locations (just as keywords, no field operator)
    if parsed_jd.locations:
        # Filter out "Remote"
        locations = [loc for loc in parsed_jd.locations if loc.lower() != "remote"]
        if locations:
            loc_query = _format_or_group(locations, quote=True)
            parts.append(f"({loc_query})")

    # Education (as keywords)
    if parsed_jd.education:
        degrees = _format_or_group(parsed_jd.education, quote=True)
        parts.append(f"({degrees})")

    # Certifications (as keywords)
    if parsed_jd.certifications:
        certs = _format_or_group(parsed_jd.certifications, quote=True)
        parts.append(f"({certs})")

    # Company exclusions using NOT
    for company in parsed_jd.companies_to_exclude:
        parts.append(f'NOT "{company}"')

    # Join all parts with AND
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


def format_query_display(
    query: str,
    platform: Platform,
    parsed_jd: ParsedJobDescription
) -> str:
    """
    Format the query for display in Slack with extracted info summary.

    Args:
        query: The Boolean query string
        platform: The platform it's formatted for
        parsed_jd: The parsed job description

    Returns:
        Formatted string for Slack display
    """
    platform_name = platform.value.title()

    lines = [
        f"*Platform: {platform_name}*",
        "",
        "```",
        query,
        "```",
        "",
        "*Extracted Information:*"
    ]

    if parsed_jd.job_titles:
        lines.append(f"- *Job Titles:* {', '.join(parsed_jd.job_titles)}")

    if parsed_jd.required_skills:
        lines.append(f"- *Required Skills:* {', '.join(parsed_jd.required_skills)}")

    if parsed_jd.preferred_skills:
        lines.append(f"- *Preferred Skills:* {', '.join(parsed_jd.preferred_skills)}")

    if parsed_jd.experience_level:
        exp = parsed_jd.experience_level
        if parsed_jd.years_experience:
            exp += f" ({parsed_jd.years_experience} years)"
        lines.append(f"- *Experience:* {exp}")

    if parsed_jd.locations:
        lines.append(f"- *Locations:* {', '.join(parsed_jd.locations)}")

    if parsed_jd.education:
        lines.append(f"- *Education:* {', '.join(parsed_jd.education)}")

    if parsed_jd.certifications:
        lines.append(f"- *Certifications:* {', '.join(parsed_jd.certifications)}")

    if parsed_jd.companies_to_exclude:
        lines.append(f"- *Excluding:* {', '.join(parsed_jd.companies_to_exclude)}")

    # Add quick actions
    lines.extend([
        "",
        "*Quick Actions:*",
        "`platform linkedin` or `platform seekout` - Switch platform",
        "`broader` - Fewer requirements, more candidates",
        "`narrower` - More specific, fewer candidates",
        "`add [skill]` - Add a required skill",
        "`remove [skill]` - Remove a skill",
        "`clear` - Start over with a new job description"
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
