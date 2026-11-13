from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
import re

class SourceRecordSchema(BaseModel):
    """
    Schema validation for raw incoming source records.
    Enforces required keys, basic type sanity, and ISO-8601 format checking.
    """
    source_system: str = Field(..., min_length=1, description="Source system origin (e.g. crm_salesforce, billing_stripe)")
    source_record_id: str = Field(..., min_length=1, description="Primary identifier within the source system")
    national_id: Optional[str] = Field(None, description="National identifier, SSN, or Tax ID")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    legal_name: Optional[str] = Field(None, description="Legal business or full personal name")
    date_of_birth: Optional[str] = Field(None, description="Date of birth in YYYY-MM-DD format")
    postal_code: Optional[str] = Field(None, description="Postal / ZIP code")
    country: Optional[str] = Field(None, description="Country code (e.g. US, CA, UK)")
    event_timestamp: Optional[str] = Field(None, description="ISO-8601 event or extraction timestamp")
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional custom metadata")

    @field_validator("source_system", "source_record_id")
    @classmethod
    def cannot_be_blank_or_whitespace(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or purely whitespace")
        return v.strip()

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        # Must match YYYY-MM-DD
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(f"Invalid date_of_birth format '{v}', expected YYYY-MM-DD")
        return v

    @field_validator("event_timestamp")
    @classmethod
    def validate_event_timestamp(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        try:
            # Handle ISO timestamps with Z or offsets
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            raise ValueError(f"Invalid ISO-8601 event_timestamp '{v}'")
        return v

