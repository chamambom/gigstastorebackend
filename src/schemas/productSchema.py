from datetime import datetime
from typing import Optional, List
from beanie import PydanticObjectId
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


# ============= CLOUDFLARE R2 MEDIA SCHEMAS =============

# Add this new schema for the confirm upload endpoint's body
class MediaConfirmSchema(BaseModel):
    object_key: str
    file_type: str
    file_size: int


# Update MediaFile to use `type` instead of `file_type` to match the confirmation
# process and the model
class MediaFile(BaseModel):
    url: str
    object_key: str = Field(...)  # Add this line
    file_type: str  # e.g. "image", "video" -  `file_type`
    size: Optional[int] = None  # in bytes, optional
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class ProductStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


# ============= PRODUCT SCHEMAS =============
class SellerInfo(BaseModel):
    """Schema for seller information in product listings"""
    _id: str
    tradingName: str
    address: Optional[dict] = None
    overallProviderRating: Optional[float] = None
    totalProviderReviews: Optional[int] = None


class ProductCreate(BaseModel):
    """Schema for creating a product"""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10)
    price: float = Field(..., gt=0)
    category: str = Field(..., min_length=1)
    stock: int = Field(..., ge=0)  # Must be included in creation payload
    image: str
    media: List[MediaFile] = Field(default_factory=list)  # ✅ better default

    is_recurring: bool = False  # Default to false (one-time)
    # Required only if is_recurring is True
    # Options: 'day', 'week', 'month', 'year'
    interval: Optional[str] = None



class ProductUpdate(BaseModel):
    """Schema for updating a product"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=10)
    price: Optional[float] = Field(None, gt=0)
    category: Optional[str] = Field(None, min_length=1)
    # image: Optional[str] = None
    status: Optional[ProductStatus] = None
    media: List[MediaFile] = Field(default_factory=list)  # ✅ better default
    stock: Optional[int] = Field(None, ge=0)  # Must be included in update payload

    is_recurring: bool = False  # Default to false (one-time)
    # Required only if is_recurring is True
    # Options: 'day', 'week', 'month', 'year'
    interval: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,  # Enable from_orm to work with ORM models
        from_attributes=True,  # This allows Pydantic to use aliases
    )


class ProductRead(BaseModel):
    """Schema for reading a product"""
    id: PydanticObjectId = Field(..., alias="_id")
    seller_id: PydanticObjectId
    title: str
    description: str
    price: float
    category: str
    image: str
    status: ProductStatus
    created_at: datetime
    updated_at: datetime
    seller: Optional[SellerInfo] = None  # Include seller info
    media: List[MediaFile] = Field(default_factory=list)  # ✅ better default
    is_recurring: bool = False  # Default to false (one-time)
    # Required only if is_recurring is True
    # Options: 'day', 'week', 'month', 'year'
    interval: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,  # Enable from_orm to work with ORM models
        from_attributes=True,  # This allows Pydantic to use aliases
    )


# ============= CART SCHEMAS =============
class CartItemSchema(BaseModel):
    """Schema for cart item"""
    product_id: PydanticObjectId
    quantity: int = Field(..., gt=0)


class CartAddItemRequest(BaseModel):
    """Request schema for adding to cart"""
    product_id: PydanticObjectId
    quantity: int = Field(default=1, gt=0)


class CartUpdateItemRequest(BaseModel):
    """Request schema for updating cart item"""
    quantity: int = Field(..., gt=0)


class CartItemWithProduct(BaseModel):
    """Cart item with full product details (for frontend)"""
    product_id: PydanticObjectId
    quantity: int
    product: ProductRead


class CartRead(BaseModel):
    """Schema for reading cart"""
    id: PydanticObjectId = Field(..., alias="_id")
    user_id: PydanticObjectId
    items: List[CartItemWithProduct]
    total_items: int
    total_price: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        populate_by_name=True,  # Enable from_orm to work with ORM models
        from_attributes=True,  # This allows Pydantic to use aliases
    )


# ============= WISHLIST SCHEMAS =============
class WishlistItemSchema(BaseModel):
    """Schema for wishlist item"""
    product_id: PydanticObjectId
    added_at: datetime


class WishlistRead(BaseModel):
    """Schema for reading wishlist"""
    id: PydanticObjectId = Field(..., alias="_id")
    user_id: PydanticObjectId
    items: List[ProductRead]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True)


# ============= ORDER SCHEMAS =============
class OrderItemRead(BaseModel):
    """Order item for history"""
    product_id: PydanticObjectId
    quantity: int
    product_title: str
    product_price: float


class OrderRead(BaseModel):
    """Schema for reading orders"""
    id: PydanticObjectId = Field(..., alias="_id")
    user_id: PydanticObjectId
    items: List[OrderItemRead]
    total_amount: float
    status: str
    stripe_payment_intent_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        populate_by_name=True,  # Enable from_orm to work with ORM models
        from_attributes=True,  # This allows Pydantic to use aliases
    )


# ============= ERROR RESPONSE SCHEMAS =============
class ErrorResponse(BaseModel):
    """Standardized error response"""
    error_code: str
    detail: str
    status_code: int
