from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated

# Assuming you have these imports for auth and services
from src.crud.userService import get_user_manager, UserManager
from src.routes.userRoute import current_active_user  # Ensure this dependency exists
from src.config.settings import settings
from src.models.userModel import User, StripeProviderStatus  # Import your User model and ProviderStatus enum
import stripe
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize Stripe
stripe.api_key = settings.stripe_keys["secret_key"]  # Use your configured secret key


# Ensure only superusers/admins can access
def require_admin(user: User = Depends(current_active_user)):
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return user


@router.delete("/admin/provider/{user_id}/reset-stripe-connect",
               summary="Admin: Delete Stripe Connect Account and Reset Provider Status",
               response_model=dict,
               status_code=status.HTTP_200_OK)
async def admin_reset_stripe_connect(
        user_id: str,
        admin: User = Depends(require_admin),  # Ensure only superusers can access this
        user_manager: UserManager = Depends(get_user_manager)
):
    """
    For testing: Deletes the Stripe Connect account AND the Stripe Customer
    associated with a user, and resets the user's Stripe-related fields and
    provider status in the database.
    """
    logger.info(f"Admin {admin.email} is initiating Connect/Customer reset for user ID: {user_id}")

    # 1. Retrieve the target user
    user_to_reset = await user_manager.get(user_id)
    if not user_to_reset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found."
        )

    connect_account_id = user_to_reset.stripe_connect_account_id
    customer_id = user_to_reset.stripe_customer_id # <--- Get Customer ID here

    # 2. Delete the Stripe Connect Account (if one exists)
    if connect_account_id:
        try:
            # Use the Stripe API call as you found it
            deleted_account = stripe.Account.delete(connect_account_id)
            logger.info(f"✅ Deleted Stripe Connect Account: {deleted_account.id}")

        except stripe.error.InvalidRequestError as e:
            # Catch common errors like "No such account" (account already deleted)
            if 'No such account' in str(e):
                logger.warning(f"Stripe account {connect_account_id} not found on Stripe, proceeding.")
            else:
                logger.error(f"Failed to delete Stripe account {connect_account_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during Stripe Account deletion: {e}")
            pass

    # 2b. Delete the Stripe Customer (if one exists) <--- NEW LOGIC STARTS HERE
    if customer_id:
        try:
            # First, ensure any active subscription is canceled, as the customer
            # deletion API often fails if an active subscription exists.
            if user_to_reset.stripe_subscription_id:
                try:
                    stripe.Subscription.delete(user_to_reset.stripe_subscription_id)
                    logger.info(f"✅ Canceled Subscription {user_to_reset.stripe_subscription_id} for customer {customer_id}.")
                except stripe.error.InvalidRequestError as e:
                    # Log but continue if sub is already canceled/no longer exists
                    logger.warning(f"Failed to cancel subscription {user_to_reset.stripe_subscription_id}: {e}")

            # Now, delete the customer. This typically cleans up associated objects
            # like Payment Methods automatically.
            deleted_customer = stripe.Customer.delete(customer_id)
            logger.info(f"✅ Deleted Stripe Customer: {deleted_customer.id}")

        except stripe.error.InvalidRequestError as e:
            # Catch errors like "No such customer"
            if 'No such customer' in str(e):
                logger.warning(f"Stripe customer {customer_id} not found on Stripe, proceeding.")
            else:
                logger.error(f"Failed to delete Stripe customer {customer_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during Stripe Customer deletion: {e}")
            pass # Proceed to reset local DB fields even if Stripe failed

    # 3. Reset Local Database Fields
    # Reset all fields related to the provider status and Connect
    user_to_reset.stripe_connect_account_id = None

    # Reset subscription/customer fields for a full reset:
    user_to_reset.stripe_customer_id = None # <--- Nullify the customer ID
    user_to_reset.stripe_subscription_id = None
    user_to_reset.stripe_subscription_price_id = None

    # Reset provider status to the very beginning of the onboarding flow
    # (Assuming ProviderStatus.NOT_STARTED is correct for your model)
    user_to_reset.stripe_provider_status = StripeProviderStatus.NOT_STARTED

    # Optionally reset onboarding flags if you want the provider to redo the whole flow
    if user_to_reset.onboarding_status:
        user_to_reset.onboarding_status.stripe_activate_subscription_complete = False

    await user_to_reset.save()
    logger.info(f"✅ Local DB fields reset for user {user_id}.")

    return {
        "message": f"Stripe Connect Account and Customer deleted (if found) and user {user_id} reset to NOT_STARTED status.",
        "user_id": user_id
    }

@router.delete("/admin/stripe/connect-account/{account_id}",
               summary="Admin: Directly Delete a Stripe Connect Account by ID",
               response_model=dict,
               status_code=status.HTTP_200_OK)
async def admin_delete_stripe_connect_account(
        account_id: str,
        admin: User = Depends(require_admin),  # Ensure only superusers can access this
):
    """
    For testing/cleanup: Deletes a Stripe Connect account using its direct 'acct_...' ID.
    This does NOT interact with your local database.
    """
    if not account_id.startswith('acct_'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Account ID must start with 'acct_'"
        )

    logger.info(f"Admin {admin.email} is deleting Stripe Connect Account ID: {account_id}")

    try:
        # 1. Attempt to delete the account via the Stripe API
        deleted_account = stripe.Account.delete(account_id)

        # Stripe returns an object with "deleted": true on success
        if deleted_account.deleted:
            logger.info(f"✅ Successfully deleted Stripe Connect Account: {account_id}")
            return {
                "message": f"Stripe Connect Account {account_id} was successfully deleted.",
                "deleted_id": account_id
            }
        else:
            # Should not happen if the call succeeds, but good for safety
            raise Exception("Stripe API call succeeded but account was not marked as deleted.")

    except stripe.error.InvalidRequestError as e:
        # Handles errors like "No such account" or "Account cannot be deleted"
        logger.error(f"Stripe API Error deleting account {account_id}: {e.user_message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stripe Error: {e.user_message}"
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting Stripe Account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete Stripe account due to an internal server error."
        )
