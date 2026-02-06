"""
Job description parser using LLM.

Extracts structured data from job descriptions for Boolean query generation.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from llm_client import call_llm, parse_json_response, LLMError, ParseError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert technical recruiter specializing in Boolean search queries.
Analyze the provided job description and extract structured information for building candidate search queries.

Your task is to identify and extract:
1. **Job Titles**: The primary title AND 2-4 alternative titles candidates might use
2. **Primary Skill**: The single most defining skill for this role - the one skill that best identifies qualified candidates
3. **Skills**: All relevant skills from the JD, ordered by importance (most critical first). Max 15 items.
4. **Experience Level**: Entry, Mid, Senior, Lead, Principal, Director, etc.
5. **Years Experience**: If mentioned (e.g., "5+", "3-5 years")
6. **Locations**: Cities, states, regions, or "Remote" if applicable
7. **Industries**: Target industries or domains
8. **Education**: Degree requirements (BS, MS, PhD, etc.)
9. **Certifications**: Required or preferred certifications
10. **Target Companies**: Types of companies to source from (based on role type, NOT competitors)
11. **Companies to Exclude**: Competitors or companies explicitly mentioned to avoid

IMPORTANT GUIDELINES:
- For job titles, think like a recruiter: what variations would real candidates use?
  - "Software Engineer" → also "Developer", "Programmer", "SWE"
  - "Senior" → also "Sr.", "Staff", "Lead"
- The primary_skill should be the ONE skill that most defines this role
- Order the skills list from most important to least important
- Keep skill names concise (e.g., "Python" not "Python programming language")
- Do NOT exceed 15 skills total

Return ONLY valid JSON with this exact structure:
{
  "job_titles": ["Primary Title", "Alt Title 1", "Alt Title 2"],
  "primary_skill": "The single most essential skill",
  "skills": ["skill1", "skill2", "skill3", "...up to 15"],
  "experience_level": "Senior",
  "years_experience": "5+",
  "locations": ["City1", "State1", "Remote"],
  "industries": ["industry1", "industry2"],
  "education": ["Bachelor's", "Master's"],
  "certifications": ["cert1", "cert2"],
  "target_companies": ["type of company to source from"],
  "companies_to_exclude": ["competitor1", "competitor2"]
}

If a field has no information, use an empty list [] or null for strings."""


@dataclass
class ParsedJobDescription:
    """Structured data extracted from a job description."""
    job_titles: list[str] = field(default_factory=list)
    primary_skill: Optional[str] = None
    skills: list[str] = field(default_factory=list)
    experience_level: Optional[str] = None
    years_experience: Optional[str] = None
    locations: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    target_companies: list[str] = field(default_factory=list)
    companies_to_exclude: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ParsedJobDescription":
        """Create from dictionary."""
        # Support legacy format with required_skills/preferred_skills
        if "required_skills" in data or "preferred_skills" in data:
            skills = data.get("required_skills", []) + data.get("preferred_skills", [])
            primary_skill = skills[0] if skills else None
        else:
            skills = data.get("skills", [])
            primary_skill = data.get("primary_skill")

        return cls(
            job_titles=data.get("job_titles", []),
            primary_skill=primary_skill,
            skills=skills,
            experience_level=data.get("experience_level"),
            years_experience=data.get("years_experience"),
            locations=data.get("locations", []),
            industries=data.get("industries", []),
            education=data.get("education", []),
            certifications=data.get("certifications", []),
            target_companies=data.get("target_companies", []),
            companies_to_exclude=data.get("companies_to_exclude", [])
        )

    def is_empty(self) -> bool:
        """Check if no useful data was extracted."""
        return not self.job_titles and not self.skills


def parse_job_description(text: str) -> ParsedJobDescription:
    """
    Parse a job description and extract structured data.

    Args:
        text: Raw job description text

    Returns:
        ParsedJobDescription with extracted fields

    Raises:
        LLMError: If the LLM call fails
        ParseError: If the response cannot be parsed
    """
    if len(text) < 20:
        raise ParseError("Job description is too short. Please provide more details.")

    if len(text) > 15000:
        # Truncate very long JDs
        text = text[:15000] + "\n...[truncated]"
        logger.warning("Job description truncated to 15000 characters")

    try:
        response = call_llm(SYSTEM_PROMPT, text)
        data = parse_json_response(response)
        parsed = ParsedJobDescription.from_dict(data)

        if parsed.is_empty():
            raise ParseError(
                "Could not extract job titles or skills. "
                "Please ensure the text is a valid job description."
            )

        logger.info(
            f"Parsed JD: {len(parsed.job_titles)} titles, "
            f"primary_skill={parsed.primary_skill}, "
            f"{len(parsed.skills)} skills"
        )

        return parsed

    except LLMError:
        raise
    except ParseError:
        raise
    except Exception as e:
        logger.exception("Unexpected error parsing job description")
        raise ParseError(f"Failed to parse job description: {e}")


def apply_refinement(
    current: ParsedJobDescription,
    instruction: str
) -> ParsedJobDescription:
    """
    Apply a refinement instruction to an existing parsed JD.

    Args:
        current: Current ParsedJobDescription
        instruction: User's refinement instruction (e.g., "add Python", "remove AWS")

    Returns:
        Updated ParsedJobDescription

    Raises:
        LLMError: If the LLM call fails
        ParseError: If the response cannot be parsed
    """
    refinement_prompt = f"""You are modifying an existing Boolean search configuration based on user feedback.

Current configuration:
{current.to_dict()}

User instruction: "{instruction}"

Apply the user's instruction to modify the configuration. Common instructions:
- "add [skill]" - Add to the skills list
- "remove [skill]" - Remove from the skills list
- "change titles" - Modify job titles

Return the COMPLETE updated configuration as JSON (same structure as input).
Only modify what the user requested - preserve everything else."""

    try:
        response = call_llm(
            "You are a Boolean search configuration assistant. Return only valid JSON.",
            refinement_prompt,
            temperature=0.2
        )
        data = parse_json_response(response)
        return ParsedJobDescription.from_dict(data)

    except Exception as e:
        logger.exception("Error applying refinement")
        raise ParseError(f"Failed to apply refinement: {e}")
