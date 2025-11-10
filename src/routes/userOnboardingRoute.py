import stripe
from fastapi import APIRouter, Depends, HTTPException, status, Body
from src.crud.userService import current_active_user, get_user_manager, \
    UserManager  # Dependency to get the current authenticated user
from src.models.userModel import User, OnboardingStatus, Address  # Ensure these are imported
from src.routes.stripeSubscriptionServices import create_stripe_customer  # Import the refactored function
from src.commonUtils.emailUtil import send_email  # Import your email sending service
from src.commonUtils.computeLocationUtil import compute_location  # Your helper for location
from src.schemas.userSchema import UserRead, ProviderOnboarding
from pydantic import BaseModel, Field
from src.commonUtils.enumUtils import StripeProviderStatus
from src.commonUtils.email_renderer import get_welcome_onboarding_complete_email
from src.config.settings import settings
from datetime import datetime, UTC
import logging

logger = logging.getLogger(__name__)

frontend_url = settings.FRONTEND_URL

router = APIRouter()  # Ensure your router is instantiated
solo_hustle_price_id = settings.stripe_keys["stripe_price_id_solo_hustle"]


class BasicProfileUpdate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)  # Required fields
    phone_number: str = Field(..., min_length=7, max_length=20)  # Required fields
    address: dict | None = None  # Assuming address comes as a dict, will be validated by Address model


# ==========================================================
# A. PROVIDER ONBOARDING ROUTES
# ==========================================================


@router.post("/user/onboarding/activate-stripe-subscription", response_model=UserRead, status_code=status.HTTP_200_OK)
async def activate_subscription_endpoint(
        user: UserRead = Depends(current_active_user)
):
    """
        Creates Stripe Customer + Subscription, then marks user as ready for Connect.
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
    if user.onboarding_status.stripe_activate_subscription_complete:
        print(f"Stripe Subscription setup already complete for user {user.id}.")
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
        user.onboarding_status.stripe_activate_subscription_complete = True
        # --- START OF REQUIRED CHANGE ---
        # Set the provider status to APPROVED: Platform process is complete, now waiting for Stripe webhook.
        # Assuming ProviderStatus.APPROVED is the state you want to transition to.
        user.stripe_provider_status = StripeProviderStatus.ACTIVATE_SUBSCRIPTION_COMPLETE
        # --- END OF REQUIRED CHANGE ---
        await user.save()  # Persist all changes to the database
        print(f"✅ User {user.id} updated with Stripe details and activate_subscription_complete flag.")

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
            detail="Failed to complete billing setup due to an internal server error. Please try again or contact "
                   "support."
        )


# ==========================INTERNAL PROVIDER ONBOARDING================================

@router.post("/user/onboarding/provider", response_model=UserRead)
async def complete_provider_onboarding(
        provider_data: ProviderOnboarding,
        user: User = Depends(current_active_user),  # Default
        user_manager: UserManager = Depends(get_user_manager)  # Default
):
    user = await user_manager.complete_provider_onboarding(user, provider_data)
    return user  # Must match UserRead


@router.put("/user/onboarding/complete-basic-profile",
            response_model=UserRead)  # Ensure User is your Pydantic model for response
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
    # user.onboarding_status.activate_subscription_complete = False # Ensure these are NOT set here

    # Do NOT add 'provider' role here
    # Do NOT initiate Stripe here

    await user.save()  # Assuming user.save() persists changes to the database
    return user  # Return the updated user object


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


# class StatusUpdatePayload(BaseModel):
#     """
#     Pydantic model for the payload when updating a user's provider status.
#     The client sends this to trigger the final status transition.
#     """
#     # The status must be one of the defined ProviderStatus values.
#     # The client will send "pending_requirements" at the final step.
#     stripe_provider_status: StripeProviderStatus = Field(
#         ...,
#         description="The desired new status for the provider (must be a valid ProviderStatus enum value)."
#     )
#
#     class Config:
#         # Allows reading models from Enums, useful for response bodies
#         use_enum_values = True
#         json_schema_extra = {
#             "example": {
#                 "stripe_provider_status": "pending_requirements"
#             }
#         }


# RECOMMENDED BACKEND IMPLEMENTATION
# @router.patch("/user/set-provider-status", status_code=status.HTTP_200_OK)
# async def set_stripe_provider_status(
#         payload: StatusUpdatePayload,  # Use a Pydantic model to read the payload
#         user: User = Depends(current_active_user)
# ):
#     # Security: Ensure the client is only asking to transition to a valid
#     # status, like PENDING_REQUIREMENTS, at this step.
#     if payload.stripe_provider_status != ProviderStatus.CONNECT_VERIFICATION_PENDING:
#         raise HTTPException(status_code=400, detail="Invalid status transition for this endpoint.")
#
#     # 1. Update the stripe_provider_status
#     user.stripe_provider_status = ProviderStatus.CONNECT_VERIFICATION_PENDING
#
#     # 2. Update the onboarding status (optional, but confirms the step is done)
#     user.onboarding_status.activate_subscription_complete = True
#
#     await user.save()
#
#     # Return the new status to be safe
#     return {"message": "Application submitted for final verification.", "stripe_provider_status": user.stripe_provider_status}


# Example of a protected route using the new dependency
@router.get("/protected-route", response_model=dict)
async def protected_route(user: User = Depends(requires_onboarding_complete)):
    return {"message": f"Welcome onboarded user {user.full_name}!"}


# ==========================================================
# B. STRIPE EXPRESS ONBOARDING ROUTES
# ==========================================================

# Initialize Stripe (using your existing key setup)
stripe.api_key = settings.stripe_keys["secret_key"]
from fastapi.responses import JSONResponse


# ==========================STRIPE REDIRECT================================

@router.post("/user/onboarding/initiate-payouts", response_model=dict)
async def initiate_payouts_setup(
        user: User = Depends(current_active_user),
        user_manager: UserManager = Depends(get_user_manager)
):
    """
        Creates Stripe Connect account and returns onboarding link.

    """

    # Use existing account if one was already created but the flow wasn't completed
    account_id = user.stripe_connect_account_id

    try:
        if not account_id:
            # 1. Create the Express Account (if it doesn't exist)
            account = stripe.Account.create(
                type='express',
                country='NZ',  # Use the correct country code (matching your config)
                email=user.email,
                capabilities={
                    'card_payments': {'requested': True},
                    'transfers': {'requested': True}
                },
                metadata={
                    "internal_user_id": str(user.id)  # Link back to your user
                }
            )
            account_id = account.id

            # Update the user record with the new Connect Account ID immediately
            user.stripe_connect_account_id = account_id
            user.stripe_provider_status = StripeProviderStatus.CONNECT_VERIFICATION_PENDING

            # ✅ Track when Connect was initiated
            if not user.onboarding_status.stripe_connect_initiated_at:
                user.onboarding_status.stripe_connect_initiated_at = datetime.now(UTC)

            await user.save()

        # 2. Create the Account Link for Redirection
        # This link sends the provider to the Stripe-hosted onboarding form
        account_link = stripe.AccountLink.create(
            account=account_id,
            refresh_url=settings.FRONTEND_URL + "/activate-stripe-subscription",  # You must define these URLs
            return_url=settings.FRONTEND_URL + "/awaiting-verification",  # Provider lands here after setup
            type='account_onboarding',
            collection_options={'fields': 'currently_due'},
        )

        return JSONResponse({
            "message": "Redirecting provider to Stripe for payout setup.",
            "redirect_url": account_link.url
        })

    except stripe.error.StripeError as e:
        # Log the error (e.g., logger.error(e))
        raise HTTPException(
            status_code=400,
            detail=f"Stripe onboarding error. Please try again later. ({str(e)})"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


# ===============================STRIPE EMBEDDED=======================================


@router.post("/user/onboarding/initiate-payouts-embedded", response_model=dict)
async def initiate_payouts_embedded(
        user: User = Depends(current_active_user)
):
    """
    Returns a client secret for embedded Connect onboarding.
    Used for in-app drawer experience.

    IDEMPOTENT: Safe to call multiple times - returns existing account if present.
    """
    account_id = user.stripe_connect_account_id

    try:
        # If account already exists, check its status first
        if account_id:
            try:
                account = stripe.Account.retrieve(account_id)

                # If already active, don't create a new session
                if account.get('charges_enabled') and account.get('payouts_enabled'):
                    logger.warning(f"⚠️ User {user.email} already has active Connect account")
                    raise HTTPException(
                        status_code=400,
                        detail="Your account is already verified. Please refresh the page."
                    )

                # Account exists but not complete - continue to create new session
                logger.info(f"🔄 Existing Connect account {account_id} found for {user.email}, creating new session")

            except stripe.error.InvalidRequestError:
                # Account was deleted or invalid, clear it and create new one
                logger.warning(f"⚠️ Invalid Connect account {account_id} for {user.email}, creating new one")
                account_id = None
                user.stripe_connect_account_id = None

        # Create new Express Account if needed
        if not account_id:
            account = stripe.Account.create(
                type='express',
                country='NZ',
                email=user.email,
                capabilities={
                    'card_payments': {'requested': True},
                    'transfers': {'requested': True}
                },
                metadata={
                    "internal_user_id": str(user.id)
                }
            )
            account_id = account.id

            # Update user with Connect account ID
            user.stripe_connect_account_id = account_id
            user.stripe_provider_status = StripeProviderStatus.CONNECT_VERIFICATION_PENDING

            # Track when Connect was initiated
            if not user.onboarding_status.stripe_connect_initiated_at:
                user.onboarding_status.stripe_connect_initiated_at = datetime.now(UTC)

            await user.save()
            logger.info(f"✅ Created new Connect account {account_id} for {user.email}")

        # Create AccountSession for embedded components
        account_session = stripe.AccountSession.create(
            account=account_id,
            components={
                'account_onboarding': {
                    'enabled': True,
                    'features': {
                        'external_account_collection': True
                    }
                }
            }
        )

        logger.info(f"✅ Created embedded AccountSession for {user.email} (account: {account_id})")

        return JSONResponse({
            "client_secret": account_session.client_secret,
            "account_id": account_id,
            "publishable_key": settings.stripe_keys["publishable_key"]
        })

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating embedded session for {user.email}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Stripe error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in initiate_payouts_embedded: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


# =================================STRIPE RESUME========================================


@router.post("/user/onboarding/resume-stripe-connect", response_model=dict)
async def resume_stripe_connect_onboarding(
        user: User = Depends(current_active_user)
):
    """
    Generates a new Stripe Connect onboarding link for users who didn't complete it.
    Can be used if user closes tab, or after webhook timeout.
    """
    if not user.stripe_connect_account_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe Connect account found. Please contact support."
        )

    # Only allow resume for users still in pending state
    if user.stripe_provider_status != StripeProviderStatus.CONNECT_VERIFICATION_PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume onboarding. Current status: {user.stripe_provider_status}"
        )

    try:
        # Check if account still exists and needs onboarding
        account = stripe.Account.retrieve(user.stripe_connect_account_id)

        # Check if account is already fully verified
        if account.get('charges_enabled') and account.get('payouts_enabled'):
            # Account is actually ready! Update status
            user.stripe_provider_status = StripeProviderStatus.ACTIVE
            await user.save()
            logger.info(f"✅ Provider {user.email} was already verified. Status updated to ACTIVE.")

            return JSONResponse({
                "message": "Account is already verified!",
                "redirect_url": settings.FRONTEND_URL + "/provider-dashboard"
            })

        # Generate a new AccountLink for the existing Connect account
        account_link = stripe.AccountLink.create(
            account=user.stripe_connect_account_id,
            refresh_url=settings.FRONTEND_URL + "/awaiting-verification",
            return_url=settings.FRONTEND_URL + "/awaiting-verification",
            type='account_onboarding',
            collection_options={'fields': 'currently_due'},
        )

        logger.info(f"🔄 Generated resume link for provider {user.email}")

        return JSONResponse({
            "message": "Stripe Connect onboarding link regenerated.",
            "redirect_url": account_link.url
        })

    except stripe.error.InvalidRequestError as e:
        # Account might have been deleted or is invalid
        logger.error(f"Stripe account {user.stripe_connect_account_id} is invalid: {e}")
        raise HTTPException(
            status_code=400,
            detail="Your Stripe Connect account appears to be invalid. Please contact support."
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error generating resume link for {user.email}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Stripe error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in resume_stripe_connect for {user.email}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )


@router.post("/user/onboarding/resume-stripe-connect-embedded", response_model=dict)
async def resume_stripe_connect_embedded(
        user: User = Depends(current_active_user)
):
    """
    Generates a NEW client_secret for embedded Connect onboarding resume.
    Use this when user abandons flow and needs to continue in-app.

    BEST PRACTICE: Use embedded flow for consistent UX vs redirect-based AccountLink.
    """
    if not user.stripe_connect_account_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe Connect account found. Please start the onboarding process first."
        )

    # Only allow resume for users still in pending state
    if user.stripe_provider_status != StripeProviderStatus.CONNECT_VERIFICATION_PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume onboarding. Current status: {user.stripe_provider_status}"
        )

    try:
        # Verify account still exists and needs onboarding
        account = stripe.Account.retrieve(user.stripe_connect_account_id)

        # Check if account is already fully verified (edge case)
        if account.get('charges_enabled') and account.get('payouts_enabled'):
            user.stripe_provider_status = StripeProviderStatus.ACTIVE
            await user.save()
            logger.info(f"✅ Provider {user.email} was already verified during resume. Status updated to ACTIVE.")

            return JSONResponse({
                "status": "already_verified",
                "message": "Account is already verified!",
                "redirect_url": settings.FRONTEND_URL + "/provider-dashboard"
            })

        # Generate NEW AccountSession for embedded components (fresh session)
        account_session = stripe.AccountSession.create(
            account=user.stripe_connect_account_id,
            components={
                'account_onboarding': {
                    'enabled': True,
                    'features': {
                        'external_account_collection': True
                    }
                }
            }
        )

        logger.info(f"🔄 Generated embedded resume session for provider {user.email}")

        return JSONResponse({
            "status": "resume_ready",
            "client_secret": account_session.client_secret,
            "account_id": user.stripe_connect_account_id,
            "publishable_key": settings.stripe_keys["publishable_key"]
        })

    except stripe.error.InvalidRequestError as e:
        # Account might have been deleted or is invalid
        logger.error(f"Stripe account {user.stripe_connect_account_id} is invalid: {e}")
        raise HTTPException(
            status_code=400,
            detail="Your Stripe Connect account appears to be invalid. Please contact support."
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error generating resume session for {user.email}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Stripe error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in resume_stripe_connect_embedded for {user.email}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )


# ==========================STRIPE CONNECT STATUS CHECK======================================

@router.post("/user/onboarding/check-connect-status", response_model=UserRead)
async def check_connect_status(
        user: User = Depends(current_active_user)
):
    """
    Manually checks Stripe Connect account status and updates user accordingly.
    Useful if webhook delivery fails or is delayed.

    Returns the updated user object.
    """
    if not user.stripe_connect_account_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe Connect account found. You haven't initiated payout setup yet."
        )

    try:
        # Fetch the latest account status from Stripe
        account = stripe.Account.retrieve(user.stripe_connect_account_id)

        charges_enabled = account.get('charges_enabled', False)
        payouts_enabled = account.get('payouts_enabled', False)
        details_submitted = account.get('details_submitted', False)

        logger.info(
            f"Manual status check for {user.email}: "
            f"charges_enabled={charges_enabled}, payouts_enabled={payouts_enabled}, "
            f"details_submitted={details_submitted}"
        )

        # Determine the correct status based on Stripe's response
        is_fully_verified = charges_enabled and payouts_enabled

        # Only update if status actually changes (idempotency)
        old_status = user.stripe_provider_status

        if is_fully_verified:
            if user.stripe_provider_status != StripeProviderStatus.ACTIVE:
                user.stripe_provider_status = StripeProviderStatus.ACTIVE
                user.onboarding_status.stripe_activate_connect_complete = True
                await user.save()
                logger.info(f"✅ Manual check: Provider {user.email} status updated from {old_status} to ACTIVE.")
        elif details_submitted:
            # They submitted info but Stripe is still reviewing
            if user.stripe_provider_status != StripeProviderStatus.CONNECT_VERIFICATION_PENDING:
                user.stripe_provider_status = StripeProviderStatus.CONNECT_VERIFICATION_PENDING
                await user.save()
                logger.info(f"⏳ Manual check: Provider {user.email} status updated to CONNECT_VERIFICATION_PENDING.")
        else:
            # They haven't completed the Stripe form yet
            logger.warning(
                f"⚠️ Manual check: Provider {user.email} has not completed Stripe onboarding. "
                f"Status remains {user.stripe_provider_status}."
            )

        # Return the updated user
        return user

    except stripe.error.InvalidRequestError as e:
        # Account doesn't exist or is invalid
        logger.error(f"Invalid Stripe account for user {user.email}: {e}")
        raise HTTPException(
            status_code=400,
            detail="Your Stripe Connect account appears to be invalid. Please contact support."
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error checking account status for {user.email}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Stripe error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in check_connect_status for {user.email}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while checking your account status."
        )

# ==========================CODE CLEANUP BELOW REQUIRED LATER================================

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
