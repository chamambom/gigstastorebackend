from datetime import datetime, timedelta
from typing import Optional, Dict
from beanie import PydanticObjectId
from fastapi import Depends, Request, HTTPException, status
from fastapi_users import BaseUserManager, FastAPIUsers, models, exceptions
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import BeanieUserDatabase, ObjectIDIDMixin
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.clients.facebook import FacebookOAuth2
# from app.db import User, get_user_db
from src.models.userModel import User, get_user_db
from src.schemas.userSchema import ProviderOnboarding, Address, OnboardingStatus
from src.config.settings import settings
from src.commonUtils.computeLocationUtil import compute_location
from src.commonUtils.emailUtil import send_email

from src.commonUtils.email_renderer import (
    get_verification_email,
    get_password_reset_email,
    get_password_reset_confirmation_email,
    get_welcome_registration_email  # ← Add this
)

from datetime import datetime
import logging

logger = logging.getLogger(__name__)

frontend_url = settings.FRONTEND_URL
SECRET = settings.JWT_SECRET_KEY
GOOGLE_OAUTH_CLIENT_ID = settings.GOOGLE_OAUTH_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET = settings.GOOGLE_OAUTH_CLIENT_SECRET
FACEBOOK_APP_ID = settings.FACEBOOK_APP_ID
FACEBOOK_APP_SECRET = settings.FACEBOOK_APP_SECRET

google_oauth_client = GoogleOAuth2(
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,  # 👈 this is the key change
)

facebook_oauth_client = FacebookOAuth2(
    FACEBOOK_APP_ID,
    FACEBOOK_APP_SECRET,
)


class UserManager(ObjectIDIDMixin, BaseUserManager[User, PydanticObjectId]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    # We will remove the on_after_oauth_register hook for now to avoid confusion
    # and instead handle both scenarios in a single, more robust on_after_register hook.
    # This simplifies the logic.
    async def on_after_register(
            self, user: User, request: Optional[Request] = None
    ):

        print(f"User {user.id} has registered.")

        # By default, a new user is active but not verified.
        # user.is_active = True
        # user.is_verified = False

        user.is_provisional = True
        user.roles = ["user"]
        user.onboarding_status = {
            "basic_complete": False,
            "provider_onboarding_complete": False,
            "billing_setup_complete": False
        }

        # Check if the user has one or more OAuth accounts.
        # This indicates they registered via Google or Facebook.
        is_oauth_user = False
        if user.oauth_accounts:
            # ✅ For OAuth users, mark is_oauth_registered to true
            user.is_oauth_registered = True
            user.is_verified = True
            is_oauth_user = True
            # # Also, set their hashed password to None to prevent traditional login.
            # user.hashed_password = None
            # print(f"User {user.id} registered via OAuth. Hashed password set to None and is_verified set to True.")
            print(f"User {user.id} registered via OAuth. Email verified automatically.")

        else:
            print(f"User {user.id} registered via traditional method.")
        await user.save()

        print(
            f"DEBUG: User {user.id} state after save in on_after_register: "
            f"is_active={user.is_active}, is_verified={user.is_verified}"
        )
        # print(f"DEBUG: Onboarding status after save: {user.onboarding_status.model_dump()}")  # ADD THIS LINE

        # Send welcome email
        try:
            html_content = get_welcome_registration_email(
                user_email=user.email,
                user_name=user.full_name,
                is_oauth_user=is_oauth_user,
                frontend_url=settings.FRONTEND_URL
            )

            await send_email(
                email=user.email,
                subject=f"Welcome to {settings.PLATFORM_NAME or 'GigstaStore'}! 🎉",
                message=html_content
            )

            print(f"✅ Welcome email sent to {user.email}")

        except Exception as e:
            # Don't fail registration if welcome email fails
            print(f"⚠️  Failed to send welcome email to {user.email}: {e}")
            # Optionally log to your error tracking system
            import logging
            logging.error(f"Welcome email failed for {user.email}: {str(e)}")

    async def on_after_forgot_password(
            self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"DEBUG: Entering on_after_forgot_password for user {user.email}")  # ADD THIS LINE

        html_content = get_password_reset_email(
            user_email=user.email,
            user_name=user.full_name,
            token=token,
            frontend_url=frontend_url
        )
        await send_email(
            email=user.email,
            subject="Password Reset Request",
            message=html_content
        )
        print(f"📧 Sent password reset email to {user.email} (from on_after_forgot_password)")  # ADD THIS LINE

    async def on_after_request_verify(
            self, user: User, token: str, request: Optional[Request] = None
    ):
        # Add these new, very explicit debug prints at the absolute start
        print("=" * 50)
        print(f"DEBUG: >>> ENTERING on_after_request_verify <<<")
        print(f"DEBUG: User object: {user}")
        print(f"DEBUG: User email: {user.email}")
        print(f"DEBUG: User ID: {user.id}")
        print(f"DEBUG: User is_active: {user.is_active}")  # Check if user is active here
        print(f"DEBUG: Received token: {token}")  # Check what token is actually passed
        print("=" * 50)

        # Define cooldown period (e.g., 60 seconds)
        # cooldown_period = timedelta(seconds=60)
        #
        # # Check if a verification email was sent too recently
        # if user.last_verify_request and (datetime.utcnow() - user.last_verify_request) < cooldown_period:
        #     print(f"DEBUG: Skipping email for {user.email} due to cooldown period.")
        #     print("=" * 50)
        #     return  # Silently exit without sending the email or raising an error

        # verify_link = f"{frontend_url}/verify-email?token={token}"
        # html_content = f"""
        #         <p>Hi,</p>
        #         <p>Thank you for registering. Please verify your email by clicking the link below:</p>
        #         <p><a href="{verify_link}">Verify Email</a></p>
        #         <p>If you did not register, you can ignore this email.</p>
        #         """
        html_content = get_verification_email(
            user_email=user.email,
            user_name=user.full_name,
            token=token,
            frontend_url=frontend_url
        )

        try:
            await send_email(
                email=user.email,
                subject="Verify Your Gigsta Email",
                message=html_content
            )
            print(f"📧 Sent verification email to {user.email} (from on_after_request_verify)")
        except Exception as e:
            print(f"ERROR: Failed to send verification email from on_after_request_verify to {user.email}. Error: {e}")
        print(f"DEBUG: <<< EXITING on_after_request_verify >>>")
        print("=" * 50)

    # Modified complete_provider_onboarding function
    # Assuming 'self' refers to an instance with user_db access, like a service class.
    async def complete_provider_onboarding(self, user: User, provider_data: ProviderOnboarding) -> User:
        """
        Completes provider-specific onboarding for a given user.
        This now focuses ONLY on provider-specific data and setting provider_onboarding_complete.
        It does NOT handle basic_complete (that's for /user/complete-basic-profile)
        or Stripe customer creation/billing setup (that's for /user/complete-billing-setup).
        """

        update_data = provider_data.model_dump(exclude_unset=True)

        # Update fields that might still be passed here or are relevant for this step
        # These fields are *collected* here, but basic_complete is set by the dedicated basic profile endpoint.
        if "full_name" in update_data and update_data["full_name"] is not None:
            user.full_name = update_data["full_name"]
        if "phone_number" in update_data and update_data["phone_number"] is not None:
            user.phone_number = update_data["phone_number"]

        # Handle Address and Location (if still provided here)
        if "address" in update_data and update_data["address"] is not None:
            if user.address is None:
                user.address = Address(**update_data["address"])
            else:
                for key, value in update_data["address"].items():
                    if hasattr(user.address, key):
                        setattr(user.address, key, value)
                    else:
                        print(f"Warning: Attempted to set non-existent attribute '{key}' on Address model.")
            user.location = compute_location(user.address.model_dump())
        else:
            # If address is explicitly removed or not provided, clear location
            user.location = None

        # This is the primary field for this specific provider onboarding step
        if "tradingName" in update_data and update_data["tradingName"] is not None:
            user.tradingName = update_data["tradingName"]

        # Ensure user.onboarding_status is an OnboardingStatus model instance
        if not isinstance(user.onboarding_status, OnboardingStatus):
            if user.onboarding_status is None:
                user.onboarding_status = OnboardingStatus()
            elif isinstance(user.onboarding_status, dict):
                user.onboarding_status = OnboardingStatus(**user.onboarding_status)
            else:
                print(f"Warning: Unexpected type for onboarding_status: {type(user.onboarding_status)}")
                user.onboarding_status = OnboardingStatus()

        # `is_provisional` should be set to False when they complete *any* of the initial onboarding steps
        # after choosing their path. Setting it here is acceptable.
        user.is_provisional = False

        # --- THIS IS THE CRITICAL CHANGE based on your business rule ---
        # If the provider onboarding form collects basic details (name, phone, address),
        # then setting basic_complete to True here is correct for the provider's journey.
        user.onboarding_status.basic_complete = True

        # This is the key flag this function is responsible for setting
        user.onboarding_status.provider_onboarding_complete = True

        # Do NOT set billing_setup_complete here
        # Do NOT call create_stripe_customer here

        # Add 'provider' role if not already present
        if "provider" not in user.roles:
            user.roles.append("provider")

        await user.save()

        # REMOVE ALL STRIPE INITIALIZATION LOGIC FROM HERE
        # from src.stripeRoutes.stripeSubscriptionServices import create_stripe_customer
        # await create_stripe_customer(...)

        return await self.user_db.get(user.id)  # Assuming self.user_db.get refreshes the user object

    async def authenticate(self, credentials) -> Optional[User]:
        """
        Custom authentication logic to handle users with a null hashed_password.
        """
        # First, try to find the user by their email
        try:
            user = await self.get_by_email(credentials.username)
        except exceptions.UserNotExists:
            return None  # No user found, authentication fails gracefully

        # ✅ CRITICAL LOGIC: Check if the user has a null password hash
        if user.is_oauth_registered is True:
            # Raise a specific exception that can be caught by a custom handler
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAUTH_NEEDS_PASSWORD_SETUP"  # Use a distinct error code
            )

        # Proceed with standard password verification for traditional users
        is_correct, updated_hashed_password = self.password_helper.verify_and_update(
            credentials.password, user.hashed_password
        )

        if not is_correct:
            return None  # Incorrect password

        # If password hash needs to be updated (e.g., scheme changed)
        if updated_hashed_password:
            user.hashed_password = updated_hashed_password
            await user.save()

        return user

    async def on_after_reset_password(self, user: User, request: Optional[Request] = None) -> None:
        """
        Perform logic after successful password reset.
        """
        try:
            # Reset OAuth flag if user was OAuth registered
            if user.is_oauth_registered:
                user.is_oauth_registered = False
                await user.save()
                logger.info(f"User {user.email} is_oauth_registered flag reset to False.")

            # Send password reset confirmation email
            await self._send_password_reset_confirmation_email(user)

            logger.info(f"Password reset completed successfully for user: {user.email}")

        except Exception as e:
            # Log the error but don't fail the password reset process
            logger.error(f"Error in post-password-reset processing for {user.email}: {str(e)}")
            # Optionally re-raise if you want the password reset to fail on email errors
            # raise

    async def _send_password_reset_confirmation_email(self, user: User) -> None:
        """Send confirmation email after successful password reset"""
        try:
            html_message = get_password_reset_confirmation_email(
                user_email=user.email,
                user_name=user.full_name,
                frontend_url=frontend_url
            )

            await send_email(
                email=user.email,
                subject="Password Reset Successful - Gigsta",
                message=html_message
            )

            logger.info(f"Password reset confirmation email sent successfully to {user.email}")

        except Exception as e:
            logger.error(f"Failed to send password reset confirmation email to {user.email}: {str(e)}")
            # Don't re-raise - we don't want email failures to break password reset
            pass


async def get_user_manager(user_db: BeanieUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, PydanticObjectId](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True, verified=True)
super_user = fastapi_users.current_user(active=True, verified=True, superuser=True)
# For routes that need both active AND verified
# current_verified_user = fastapi_users.current_user(verified=True)
# Or, to be absolutely explicit, which is also perfectly fine:
# current_verified_user = fastapi_users.current_user(active=True, verified=True)
