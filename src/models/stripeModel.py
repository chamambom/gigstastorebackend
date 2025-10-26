from beanie import Document
from typing import List
from src.schemas.stripeSchema import StripeSubscriptionSchemaIn


class StripeSubscriptions(Document, StripeSubscriptionSchemaIn):
    stripe_price_id: str

    class Settings:
        collection = "StripeSubscriptions"
