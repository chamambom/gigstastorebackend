from datetime import datetime
from typing import Optional, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, ConfigDict
from src.models.cartModel import CartItem
from enum import Enum


class OrderStatus(str, Enum):
    """Order status enum for better type safety"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Order(Document):
    """
    Order document representing a single checkout session.
    Each order corresponds to one seller and one payment type (one-time or recurring).
    """
    id: Optional[PydanticObjectId] = Field(None, alias="_id")
    user_id: PydanticObjectId
    seller_id: PydanticObjectId  # The seller for this order

    # Snapshot of items at time of order
    items: List[CartItem]

    # Financial details
    total_amount: float = Field(..., gt=0)
    platform_fee_amount: float = Field(default=0, ge=0)
    seller_amount: float = Field(..., gt=0)  # Amount seller receives after platform fee

    # Order metadata
    is_recurring: bool = Field(default=False)  # Whether this order contains recurring items
    status: OrderStatus = Field(default=OrderStatus.PENDING)

    # Stripe references
    stripe_checkout_session_id: Optional[str] = None  # Checkout Session ID
    stripe_payment_intent_id: Optional[str] = None  # Payment Intent ID (after completion)
    stripe_account_id: Optional[str] = None  # Connected account ID

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    class Settings:
        indexes = [
            [("user_id", 1)],
            [("seller_id", 1)],
            [("status", 1)],
            [("created_at", -1)],
            [("stripe_checkout_session_id", 1)],  # For webhook lookups
        ]

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        use_enum_values=True,  # Store enum values as strings
    )



# from datetime import datetime
# from typing import Optional, List
# from beanie import Document, PydanticObjectId
# from pydantic import BaseModel, Field, ConfigDict
# from src.models.cartModel import CartItem
# from enum import Enum
#
#
# class Order(Document):
#     """Order history for tracking"""
#     id: Optional[PydanticObjectId] = Field(None, alias="_id")
#     user_id: PydanticObjectId
#     items: List[CartItem]  # Snapshot of items at time of order
#     total_amount: float = Field(..., gt=0)
#     status: str = Field(default="pending")  # pending, completed, cancelled
#     stripe_payment_intent_id: Optional[str] = None
#     created_at: datetime = Field(default_factory=datetime.utcnow)
#     updated_at: datetime = Field(default_factory=datetime.utcnow)
#
#     class Settings:
#         indexes = [
#             [("user_id", 1)],
#             [("status", 1)],
#             [("created_at", -1)],
#         ]
#
#     model_config = ConfigDict(
#         populate_by_name=True,  # Enable from_orm to work with ORM models
#         from_attributes=True,  # This allows Pydantic to use aliases
#     )

