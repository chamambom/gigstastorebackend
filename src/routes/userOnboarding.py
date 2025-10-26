from fastapi import APIRouter, Depends, HTTPException, status, Body
from src.crud.userService import current_active_user, get_user_manager, \
    UserManager  # Dependency to get the current authenticated user
from src.models.userModel import User, OnboardingStatus, Address  # Ensure these are imported
from src.routes.stripeSubscriptionServices import create_stripe_customer  # Import the refactored function
from src.commonUtils.emailUtil import send_email  # Import your email sending service
from src.commonUtils.computeLocationUtil import compute_location  # Your helper for location
from src.schemas.userSchema import UserRead, ProviderOnboarding
from pydantic import BaseModel, Field
from src.commonUtils.enumUtils import ProviderStatus
from src.commonUtils.email_renderer import get_welcome_onboarding_complete_email
from src.config.settings import settings

frontend_url = settings.FRONTEND_URL

router = APIRouter()  # Ensure your router is instantiated
solo_hustle_price_id = settings.stripe_keys["stripe_price_id_solo_hustle"]


class BasicProfileUpdate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)  # Required fields
    phone_number: str = Field(..., min_length=7, max_length=20)  # Required fields
    address: dict | None = None  # Assuming address comes as a dict, will be validated by Address model


@router.post("/user/complete-billing-setup", response_model=UserRead, status_code=status.HTTP_200_OK)
async def complete_billing_setup_endpoint(
        user: UserRead = Depends(current_active_user)
):
    """
    Completes the billing setup for a provider by:
    1. Creating a Stripe customer and free subscription via the dedicated Stripe service.
    2. Updating the user's MongoDB record with Stripe IDs and setting billing_setup_complete.
    3. Sending a welcome/confirmation email.
    """
    # Pre-checks: Role and previous onboarding steps
    if "provider" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only providers can complete billing setup."
        )
    if not user.onboarding_status or not user.onboarding_status.provider_onboarding_complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider-specific onboarding must be complete before billing setup can be finalized."
        )
    # Idempotency check: If already complete, return early
    if user.onboarding_status.billing_setup_complete:
        print(f"Billing setup already complete for user {user.id}.")
        return user

    try:
        # Ensure user.onboarding_status is an OnboardingStatus model instance
        # This block is crucial for handling cases where onboarding_status might be None or a dict
        if not isinstance(user.onboarding_status, OnboardingStatus):
            if user.onboarding_status is None:
                user.onboarding_status = OnboardingStatus()
            elif isinstance(user.onboarding_status, dict):
                user.onboarding_status = OnboardingStatus(**user.onboarding_status)
            else:
                print(f"Warning: Unexpected type for onboarding_status: {type(user.onboarding_status)}")
                user.onboarding_status = OnboardingStatus()

        # Call the refactored create_stripe_customer function
        # This function now returns the customer_id and subscription_id
        stripe_customer_id, stripe_subscription_id = await create_stripe_customer(
            email=user.email,
            user_id=str(user.id),  # Pass user_id for Stripe metadata
            full_name=user.full_name or user.email,  # Use user's full name, fallback to email
            address=user.address.model_dump() if user.address else {}  # Pass address if available
        )

        # Update the User in MongoDB with the received Stripe details
        user.stripe_customer_id = stripe_customer_id
        user.stripe_subscription_id = stripe_subscription_id
        user.stripe_subscription_price_id = solo_hustle_price_id  # Your free plan price ID
        user.stripe_payment_method_id = ""  # This remains empty until a payment method is added

        # Mark the billing setup as complete in the user's onboarding status
        user.onboarding_status.billing_setup_complete = True
        await user.save()  # Persist all changes to the database
        print(f"✅ User {user.id} updated with Stripe details and billing_setup_complete flag.")

        # Send Welcome Email using the new template
        try:
            html_content = get_welcome_onboarding_complete_email(
                user_email=user.email,
                user_name=user.full_name,
                subscription_id=stripe_subscription_id,
                frontend_url=settings.FRONTEND_URL
            )

            await send_email(
                email=user.email,
                subject="Welcome to Gigsta - You're All Set! 🎉",
                message=html_content
            )

            print(f"✅ Welcome email sent to {user.email}")

        except Exception as e:
            print(f"⚠️  Failed to send welcome email to {user.email}: {e}")
            # Don't fail the billing setup if email fails
            pass

        return user

    except HTTPException:
        # Re-raise HTTPExceptions (e.g., from validation errors earlier in the flow)
        raise
    except Exception as e:
        # Catch any other unexpected errors during the process
        print(f"❌ Error completing billing setup for user {user.id}: {e}")
        # Log the full traceback for debugging in production
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete billing setup due to an internal server error. Please try again or contact support."
        )


@router.put("/user/complete-basic-profile", response_model=UserRead)  # Ensure User is your Pydantic model for response
async def update_basic_profile(
        profile_data: BasicProfileUpdate,
        user: UserRead = Depends(current_active_user),  # Dependency to get the current authenticated user

):
    """
    Updates basic user profile details and sets basic_complete flag.
    Does not handle provider-specific fields or Stripe.
    """
    update_data = profile_data.model_dump(exclude_unset=True)

    if "full_name" in update_data and update_data["full_name"] is not None:
        user.full_name = update_data["full_name"]
    if "phone_number" in update_data and update_data["phone_number"] is not None:
        user.phone_number = update_data["phone_number"]

    # Handle Address and Location
    if "address" in update_data and update_data["address"] is not None:
        # from src.database.models import Address  # Ensure Address model is imported
        if user.address is None:
            user.address = Address(**update_data["address"])
        else:
            for key, value in update_data["address"].items():
                if hasattr(user.address, key):
                    setattr(user.address, key, value)
        user.location = compute_location(user.address.model_dump())
    else:
        user.location = None  # Clear location if no address is provided

    # Ensure onboarding_status exists and is of correct type before updating
    # from src.database.models import OnboardingStatus  # Ensure OnboardingStatus model is imported
    if not isinstance(user.onboarding_status, OnboardingStatus):
        if user.onboarding_status is None:
            user.onboarding_status = OnboardingStatus()
        elif isinstance(user.onboarding_status, dict):
            user.onboarding_status = OnboardingStatus(**user.onboarding_status)
        else:
            print(f"Warning: Unexpected type for onboarding_status: {type(user.onboarding_status)}")
            user.onboarding_status = OnboardingStatus()

    # Crucially: ONLY set basic_complete here
    user.onboarding_status.basic_complete = True
    # user.onboarding_status.provider_onboarding_complete = False # Ensure these are NOT set here
    # user.onboarding_status.billing_setup_complete = False # Ensure these are NOT set here

    # Do NOT add 'provider' role here
    # Do NOT initiate Stripe here

    await user.save()  # Assuming user.save() persists changes to the database
    return user  # Return the updated user object


@router.post("/user/onboarding/provider", response_model=UserRead)
async def complete_provider_onboarding(
        provider_data: ProviderOnboarding,
        user: User = Depends(current_active_user),  # Default
        user_manager: UserManager = Depends(get_user_manager)  # Default
):
    user = await user_manager.complete_provider_onboarding(user, provider_data)
    return user  # Must match UserRead


# @router.post("/user/onboarding/provider", response_model=UserRead)  # Use POST for an action that "completes" a step
# async def complete_provider_onboarding_endpoint(
#         provider_data: ProviderOnboarding,  # Use the specific ProviderOnboarding schema
#         user: UserRead = Depends(current_active_user),
#         user_manager: UserManager = Depends(get_user_manager)
#         # user_manager has the logic for complete_provider_onboarding
# ):
#     """
#     Completes the provider-specific onboarding for a user.
#     Updates provider-specific fields and sets provider_onboarding_complete.
#     This endpoint does NOT handle basic profile completion or billing setup.
#     """
#     if "provider" not in user.roles:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Only users with 'provider' role can complete provider onboarding."
#         )
#
#     # Ensure onboarding_status exists as an OnboardingStatus model instance
#     if not isinstance(user.onboarding_status, OnboardingStatus):
#         user.onboarding_status = OnboardingStatus(**(user.onboarding_status or {}))
#
#     # Idempotency check
#     if user.onboarding_status.provider_onboarding_complete:
#         print(f"Provider onboarding already complete for user {user.id}. Skipping operation.")
#         return user
#
#     # Use the UserManager's method to encapsulate the update logic
#     updated_user = await user_manager.complete_provider_onboarding(user, provider_data)
#     print(
#         f"User {updated_user.id} provider onboarding updated. provider_onboarding_complete: {updated_user.onboarding_status.provider_onboarding_complete}")
#     return updated_user


# # Add to userRoute.py
# async def requires_onboarding_complete(user: User = Depends(current_active_user)):
#     if user.is_provisional:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Complete onboarding to access this resource"
#         )
#     return user

# --- Helper for Router Guard (if you place this in a dependency file, keep it there) ---
# This is fine as a dependency, no refactoring needed if it's placed correctly.
async def requires_onboarding_complete(user: User = Depends(current_active_user)):
    """
    Dependency to ensure the user has completed their basic profile onboarding.
    Assumes basic_complete being True is sufficient for 'onboarding complete' for most generic routes.
    """
    if not user.onboarding_status or not user.onboarding_status.basic_complete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Basic profile onboarding must be complete to access this resource."
        )
    return user


# --- Example of Admin-only route ---  this is "submit for review" action
@router.patch("/user/set-provider-pending", status_code=status.HTTP_200_OK)
async def set_provider_pending(user: User = Depends(current_active_user)):
    # This endpoint should ideally be for an admin or part of an internal workflow, not directly user-callable
    # Unless it's triggered by a user-initiated "submit for review" action
    user.provider_status = ProviderStatus.PENDING
    await user.save()
    return {"message": "Provider status set to pending for review."}


# Example of a protected route using the new dependency
@router.get("/protected-route", response_model=dict)
async def protected_route(user: User = Depends(requires_onboarding_complete)):
    return {"message": f"Welcome onboarded user {user.full_name}!"}
