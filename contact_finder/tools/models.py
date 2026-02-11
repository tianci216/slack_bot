"""
Data models for Contact Finder function.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Company:
    """Represents a company from search results."""
    name: str
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[str] = None
    apollo_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "domain": self.domain,
            "linkedin_url": self.linkedin_url,
            "industry": self.industry,
            "employee_count": self.employee_count,
            "apollo_id": self.apollo_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Company":
        return cls(
            name=data.get("name", ""),
            domain=data.get("domain"),
            linkedin_url=data.get("linkedin_url"),
            industry=data.get("industry"),
            employee_count=data.get("employee_count"),
            apollo_id=data.get("apollo_id"),
        )


@dataclass
class Contact:
    """Represents a decision-maker contact."""
    company_name: str
    company_domain: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    email_status: Optional[str] = None  # "verified", "unverified", "hunter_found"
    linkedin_url: Optional[str] = None
    phone: Optional[str] = None
    source: str = "apollo"  # "apollo", "hunter", "apollo+hunter"

    def to_dict(self) -> dict:
        return {
            "company_name": self.company_name,
            "company_domain": self.company_domain,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "title": self.title,
            "email": self.email,
            "email_status": self.email_status,
            "linkedin_url": self.linkedin_url,
            "phone": self.phone,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Contact":
        return cls(
            company_name=data.get("company_name", ""),
            company_domain=data.get("company_domain"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            full_name=data.get("full_name"),
            title=data.get("title"),
            email=data.get("email"),
            email_status=data.get("email_status"),
            linkedin_url=data.get("linkedin_url"),
            phone=data.get("phone"),
            source=data.get("source", "apollo"),
        )

    def to_sheet_row(self) -> list[str]:
        """Convert to a row for Google Sheets."""
        return [
            self.company_name or "",
            self.company_domain or "",
            self.full_name or "",
            self.title or "",
            self.email or "",
            self.email_status or "",
            self.linkedin_url or "",
            self.phone or "",
            self.source or "",
        ]
