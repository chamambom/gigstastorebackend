from typing import Dict, Any, List
from beanie import PydanticObjectId
from fastapi import HTTPException

from src.models.stripeModel import StripeSubscriptions
from src.models.userModel import User  # Assuming User model exists
from src.schemas.stripeSchema import StripeSubscriptionSchemaOut


async def get_all_subscriptions() -> List[StripeSubscriptionSchemaOut]:
    """Fetch all available subscription plans."""
    subscriptions = await StripeSubscriptions.find_all().to_list()  # Ensure it returns a list
    return [StripeSubscriptionSchemaOut.from_orm(subscription) for subscription in subscriptions]


async def get_user_subscription(provider_id: PydanticObjectId) -> List[StripeSubscriptionSchemaOut]:
    """Fetch the given user's subscription details."""
    user = await User.get(provider_id)

    if not user or not user.stripe_subscription_price_id:
        raise HTTPException(status_code=404, detail="Subscription details not found")

    subscription = await StripeSubscriptions.find_one(
        StripeSubscriptions.stripe_price_id == user.stripe_subscription_price_id
    )

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription plan not found")

    return [StripeSubscriptionSchemaOut.from_orm(subscription)]


