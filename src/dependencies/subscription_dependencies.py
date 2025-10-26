from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List

from fastapi.params import Query

from src.crud.stripeSubscriptionPaymentsCrud import get_all_subscriptions, get_user_subscription
from src.crud.userService import current_active_user
from src.schemas.userSchema import UserRead
from src.schemas.stripeSchema import StripeSubscriptionSchemaOut

router = APIRouter()


# @router.get("/subscriptions", response_model=List[StripeSubscriptionSchemaOut])
async def fetch_all_subscriptions() -> List[StripeSubscriptionSchemaOut]:
    """Fetch all available subscription plans."""
    return await get_all_subscriptions()

# This is not needed below to be honest, will clean this later

# @router.get("/user/subscription/{provider_id}", response_model=List[StripeSubscriptionSchemaOut])
# @router.get("/user/subscription", response_model=List[StripeSubscriptionSchemaOut])
# async def fetch_user_subscription(
#         current_user: UserRead = Depends(current_active_user),
# ) -> List[StripeSubscriptionSchemaOut]:
#     """Fetch the subscription details of a given user by their ID."""
#     return await get_user_subscription(current_user.id)
