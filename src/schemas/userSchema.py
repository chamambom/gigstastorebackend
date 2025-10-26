from datetime import datetime
from typing import Optional, List

from beanie import PydanticObjectId
from fastapi_users import schemas
from pydantic import Field, field_validator, BaseModel, conlist, condecimal, ConfigDict
# Import OnboardingStatus and Address from your models file
from src.models.userModel import OnboardingStatus, Address, ProviderStatus


class UserRead(schemas.BaseUser[PydanticObjectId]):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    tradingName: Optional[str] = None
    address: Optional[Address] = None
    location: Optional[dict] = None
    roles: List[str] = ["user"]
    is_active: bool
    is_verified: bool
    is_superuser: bool
    # onboarding_status: dict
    onboarding_status: OnboardingStatus  # It should be an OnboardingStatus object
    provider_status: ProviderStatus = ProviderStatus.NOT_APPLIED
    is_provisional: bool = True  # Default for new users
    is_oauth_registered: bool = False
    created_at: datetime
    last_verify_request: datetime
    stripe_subscription_price_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_payment_method_id: Optional[str] = None

    overallProviderRating: Optional[float] = None
    totalProviderReviews: Optional[float] = None

    class Config:
        from_attributes = True  # Pydantic v2 style for ORMs


class UserCreate(schemas.BaseUserCreate):
    full_name: Optional[str] = None
    profile_picture: Optional[str] = None
    phone_number: Optional[str] = None
    tradingName: Optional[str] = Field(None, min_length=1)  # At least 1 char or None
    address: Optional[Address] = None  # This now expects the full address structure
    location: Optional[dict] = Field(None,
                                     description="GeoJSON object for geospatial queries")  # Make location Optional
    # Make these Optional, as your on_after_register will set them
    onboarding_status: Optional[OnboardingStatus] = None  # <-- CHANGE HERE
    provider_status: Optional[ProviderStatus] = None
    is_provisional: Optional[bool] = None
    is_oauth_registered: Optional[bool] = None

    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_subscription_price_id: Optional[str] = None
    stripe_payment_method_id: Optional[str] = None

    overallProviderRating: Optional[float] = None
    totalProviderReviews: Optional[float] = None


class UserUpdate(schemas.BaseUserUpdate):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    tradingName: Optional[str] = Field(None, min_length=1)  # At least 1 char or None
    address: Optional[Address] = None  # This now expects the full address structure
    location: Optional[dict] = Field(None,
                                     description="GeoJSON object for geospatial queries")  # Make location Optional
    is_provisional: Optional[bool] = None  # Allow updating provisional status
    is_oauth_registered: bool = Field(default=False)
    onboarding_status: Optional[OnboardingStatus] = None  # Allow updating the nested onboarding status
    provider_status: Optional[ProviderStatus] = None  # It should be an ProviderStatus object

    stripe_subscription_price_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_payment_method_id: Optional[str] = None


class BasicUserCreate(schemas.BaseUserCreate):
    email: str
    password: str
    # No other required fields


class ProviderOnboarding(BaseModel):
    full_name: str
    tradingName: str = Field(..., min_length=1)
    phone_number: str
    address: Address
    # onboarding_status: Optional[OnboardingStatus] = None  # Allow updating the nested onboarding status


class SetPasswordRequest(BaseModel):
    new_password: str

