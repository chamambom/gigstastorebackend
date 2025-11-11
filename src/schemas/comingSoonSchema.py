from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class ComingSoonForm(BaseModel):
    """Schema for validating coming soon form submissions."""
    name: str = Field(..., min_length=2, max_length=100, description="User's full name")
    email: EmailStr = Field(..., description="Valid email address")
    business: Optional[str] = Field(None, max_length=150, description="Business or trading name")
    phone: Optional[str] = Field(None, max_length=20, description="Contact phone number")