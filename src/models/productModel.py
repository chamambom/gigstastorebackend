from datetime import datetime
from typing import Optional, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

from src.schemas.productSchema import MediaFile


class ProductStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Product(Document):
    """Product document in MongoDB"""
    id: Optional[PydanticObjectId] = Field(None, alias="_id")
    seller_id: PydanticObjectId  # Reference to User who created the product

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10)
    price: float = Field(..., gt=0)
    category: str = Field(..., min_length=1)

    stock: int = Field(..., ge=0)  # Stock must be an integer >= 0

    # --- New Stripe Fields ---
    stripe_product_id: Optional[str] = None  # ID of the Product on the Connected Account
    stripe_price_id: Optional[str] = None  # ID of the Price object on the Connected Account
    is_recurring: bool = False  # Default to false (one-time)
    # Required only if is_recurring is True
    # Options: 'day', 'week', 'month', 'year'
    interval: Optional[str] = None
    # -------------------------

    status: ProductStatus = ProductStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    media: List[MediaFile] = Field(default_factory=list)  # ✅ better default

    class Settings:
        indexes = [
            [("seller_id", 1)],
            [("status", 1)],
            [("created_at", -1)],
            [("category", 1)],
        ]

    model_config = ConfigDict(
        populate_by_name=True,  # Enable from_orm to work with ORM models
        from_attributes=True,  # This allows Pydantic to use aliases
    )
