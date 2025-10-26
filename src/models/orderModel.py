from datetime import datetime
from typing import Optional, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, ConfigDict
from src.models.cartModel import CartItem
from enum import Enum

class Order(Document):
    """Order history for tracking"""
    id: Optional[PydanticObjectId] = Field(None, alias="_id")
    user_id: PydanticObjectId
    items: List[CartItem]  # Snapshot of items at time of order
    total_amount: float = Field(..., gt=0)
    status: str = Field(default="pending")  # pending, completed, cancelled
    stripe_payment_intent_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        indexes = [
            [("user_id", 1)],
            [("status", 1)],
            [("created_at", -1)],
        ]

    model_config = ConfigDict(populate_by_name=True)