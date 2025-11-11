from datetime import datetime
from typing import Optional, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, ConfigDict


class ComingSoonModel(Document):
    name: str
    email: str
    business: Optional[str]
    phone: Optional[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
