from beanie import PydanticObjectId
from pydantic import BaseModel, Field, ConfigDict
from typing import List


class StripeSubscriptionSchemaIn(BaseModel):
    plan: str
    name: str
    limit: int
    perks: str
    stripe_price_id: str
    plan_price: int
    # perks: List


class StripeSubscriptionSchemaOut(BaseModel):
    id: PydanticObjectId = Field(alias="_id")  # Map MongoDB _id to Pydantic id
    plan: str
    name: str
    limit: int
    stripe_price_id: str
    perks: str
    plan_price: int

    model_config = ConfigDict(
        populate_by_name=True,  # Enable from_orm to work with ORM models
        from_attributes=True,  # This allows Pydantic to use aliases
    )
