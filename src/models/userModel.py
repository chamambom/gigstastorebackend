from datetime import datetime

from beanie import Document
from typing import List, Optional
from pydantic import field_validator, model_validator, Field, BaseModel, ConfigDict
from fastapi_users.db import BaseOAuthAccount, BeanieBaseUser, BeanieUserDatabase
from src.commonUtils.enumUtils import ProviderStatus


# from fastapi_users_db_beanie import BeanieUserDatabase


class OAuthAccount(BaseOAuthAccount):
    pass


# Define the OnboardingStatus schema first, as it's a nested object
class OnboardingStatus(BaseModel):
    basic_complete: bool = False
    provider_onboarding_complete: bool = False
    billing_setup_complete: bool = False


class Address(BaseModel):
    formatted: str
    street_number: Optional[str] = None
    street: Optional[str] = None
    locality: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    postcode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    model_config = ConfigDict(
        populate_by_name=True,  # Enable from_orm to work with ORM models
        from_attributes=True,  # This allows Pydantic to use aliases
    )


class User(BeanieBaseUser, Document):
    hashed_password: Optional[str] = None
    provider_status: ProviderStatus = ProviderStatus.NOT_APPLIED
    oauth_accounts: List[OAuthAccount] = Field(default_factory=list)
    full_name: Optional[str] = None
    profile_picture: Optional[str] = None
    phone_number: Optional[str] = None
    tradingName: Optional[str] = Field(None, min_length=1)  # At least 1 char or None
    address: Optional[Address] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_verify_request: datetime = Field(default_factory=datetime.utcnow)
    location: Optional[dict] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_subscription_price_id: Optional[str] = None
    stripe_payment_method_id: Optional[str] = None
    overallProviderRating: Optional[float] = None
    totalProviderReviews: Optional[float] = None

    # Referencing the OnboardingStatus BaseModel
    onboarding_status: OnboardingStatus = Field(default_factory=OnboardingStatus)  # Crucial: Default to an instance
    roles: List[str] = Field(default=["user"])  # ["user", "provider"]
    is_provisional: bool = Field(default=True)
    is_oauth_registered: bool = Field(default=False)

    class Settings:
        indexes = [
            [("location", "2dsphere")],  # Ensure the 2dsphere index is created on the 'location' field
            [("onboarding_status.basic_complete", 1)],  # New index
            [("roles", 1)]  # Index for role-based queries
        ]
        email_collation = {"locale": "en", "strength": 2}  # Case-insensitive collation for email queries

    class Config:
        json_schema_extra = {
            "example": {
                "email": "john.doe@example.com",
                "hashed_password": "supersecretpassword",
                "tradingName": "PinkX Services",
                "address": {
                    "formatted": "123 Main St, Anytown, USA",
                    "lat": 34.052235,
                    "lng": -118.243683
                },
                "location": {
                    "type": "Point",
                    "coordinates": [-118.243683, 34.052235]
                },
                "phone_number": "+15551234567"
            }
        }


async def get_user_db():
    yield BeanieUserDatabase(User, OAuthAccount)
