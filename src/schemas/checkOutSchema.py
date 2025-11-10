from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional
from datetime import datetime
from src.config.settings import settings


frontend_url = settings.FRONTEND_URL


class CheckOutSessionRequest(BaseModel):
    """Request to create checkout sessions"""
    success_url: HttpUrl
    cancel_url: HttpUrl

    class Config:
        json_schema_extra = {
            "example": {
                "success_url": f"{frontend_url}/checkout/success",
                "cancel_url": f"{frontend_url}/cart"
            }
        }


class CheckOutSessionResponse(BaseModel):
    """Response for a single checkout session"""
    session_id: str
    client_secret: str  # For embedded checkout
    order_id: str
    seller_name: str
    total_amount: float
    platform_fee: float
    is_recurring: bool


class CheckOutGroupResponse(BaseModel):
    """Response containing all checkout sessions grouped"""
    sessions: List[CheckOutSessionResponse]
    total_groups: int
    message: str = "Checkout sessions created successfully"


class OrderItemRead(BaseModel):
    """Order item for response"""
    product_id: str
    quantity: int


class OrderRead(BaseModel):
    """Order response schema"""
    id: str
    user_id: str
    seller_id: str
    items: List[OrderItemRead]
    total_amount: float
    platform_fee_amount: float
    seller_amount: float
    is_recurring: bool
    status: str
    stripe_checkout_session_id: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CartGroupRead(BaseModel):
    """Cart group for frontend display"""
    seller_id: str
    seller_name: str
    is_recurring: bool
    group_total_price: float
    items: List[dict]  # Will contain product details


class GroupedCartResponse(BaseModel):
    """Response containing grouped cart for checkout display"""
    groups: List[CartGroupRead]
    total_groups: int
    grand_total: float