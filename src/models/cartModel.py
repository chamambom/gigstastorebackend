from datetime import datetime
from typing import Optional, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class CartItem(BaseModel):
    """Individual item in cart"""
    product_id: PydanticObjectId
    quantity: int = Field(..., gt=0)


class Cart(Document):
    """Shopping cart for a user"""
    id: Optional[PydanticObjectId] = Field(None, alias="_id")
    user_id: PydanticObjectId  # Reference to User
    items: List[CartItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        indexes = [
            [("user_id", 1)],  # Fast lookup by user
        ]

    model_config = ConfigDict(populate_by_name=True)
