from datetime import datetime
from typing import Optional, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class WishlistItem(BaseModel):
    """Individual item in wishlist"""
    product_id: PydanticObjectId
    added_at: datetime = Field(default_factory=datetime.utcnow)


class Wishlist(Document):
    """Wishlist for a user"""
    id: Optional[PydanticObjectId] = Field(None, alias="_id")
    user_id: PydanticObjectId
    items: List[WishlistItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        indexes = [
            [("user_id", 1)],
        ]

    model_config = ConfigDict(populate_by_name=True)
