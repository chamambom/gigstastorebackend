from datetime import datetime
from typing import Optional, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


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
    image: str  # URL to image

    status: ProductStatus = ProductStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        indexes = [
            [("seller_id", 1)],
            [("status", 1)],
            [("created_at", -1)],
            [("category", 1)],
        ]

    model_config = ConfigDict(populate_by_name=True)




