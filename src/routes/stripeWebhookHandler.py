# src/routers/stripe_webhooks.py
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
import stripe
import logging
from typing import Optional

from commonUtils.enumUtils import StripeProviderStatus
from src.crud.userService import get_user_manager, UserManager
from src.crud.checkOutService import CheckOutService
from src.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

stripe_webhook_secret = settings.stripe_keys["webhook_secret"]
stripe.api_key = settings.stripe_keys["secret_key"]


# ==========================================================
# 1. BACKGROUND TASK HANDLERS
# ==========================================================

async def handle_connect_account_update(
        user_manager: UserManager,
        connect_id: str,
        charges_enabled: bool,
        payouts_enabled: bool
):
    """
    Background task to handle the 'account.updated' event.
    Updates the provider's status based on Stripe's 'enabled' flags.

    Idempotency: Only updates database if status actually changes.
    """
    logger.info(f"Background Task: Starting handle_connect_account_update for Connect ID: {connect_id}")

    try:
        # Fetch user from database
        user = await user_manager.get_user_by_stripe_connect_id(connect_id)

        if not user:
            logger.warning(f"User not found for Stripe Connect ID: {connect_id}. Skipping status update.")
            return

        # Calculate the target status based on Stripe's flags
        is_fully_ready = charges_enabled and payouts_enabled

        # Determine what the new status should be
        if is_fully_ready:
            target_status = StripeProviderStatus.ACTIVE
        else:
            # If they were active but now disabled, revert to pending
            target_status = StripeProviderStatus.CONNECT_VERIFICATION_PENDING if user.stripe_provider_status == StripeProviderStatus.ACTIVE else user.stripe_provider_status

        # ✅ IDEMPOTENCY CHECK: Only update if status actually changes
        if user.stripe_provider_status == target_status:
            logger.info(
                f"ℹ️ Provider {user.email} (ID: {user.id}) already has status '{target_status}'. "
                f"No update needed. (charges_enabled={charges_enabled}, payouts_enabled={payouts_enabled})"
            )
            return  # Early return - no database write needed

        # Status is different, so we need to update
        old_status = user.stripe_provider_status
        user.stripe_provider_status = target_status
        await user.save()

        # Log the successful update with context
        if target_status == StripeProviderStatus.ACTIVE:
            user.onboarding_status.stripe_activate_connect_complete = True
            logger.info(
                f"✅ Provider {user.email} (ID: {user.id}) status updated: "
                f"{old_status} → {StripeProviderStatus.ACTIVE}. "
                f"Account is now fully enabled (charges={charges_enabled}, payouts={payouts_enabled})."
            )
        else:
            logger.warning(
                f"⚠️ Provider {user.email} (ID: {user.id}) status reverted: "
                f"{old_status} → {target_status}. "
                f"Account capabilities changed (charges={charges_enabled}, payouts={payouts_enabled})."
            )

    except Exception as e:
        logger.error(
            f"❌ Error in handle_connect_account_update for Connect ID {connect_id}: {e}",
            exc_info=True
        )


# ✅ NEW: Background task for checkout completion
async def handle_checkout_session_completed(
        session_id: str,
        stripe_account_id: Optional[str] = None
):
    """
    Background task to handle 'checkout.session.completed' event.
    Updates order status and clears cart items.

    Args:
        session_id: Stripe checkout session ID
        stripe_account_id: Connected account ID (if event is from a connected account)
    """
    logger.info(f"Background Task: Starting handle_checkout_session_completed for Session ID: {session_id}")

    try:
        # Call the CheckOutService to handle the completion
        order = await CheckOutService.handle_checkout_completion(
            session_id=session_id,
            stripe_account_id=stripe_account_id
        )

        logger.info(
            f"✅ Checkout completed successfully. "
            f"Order ID: {order.id}, User ID: {order.user_id}, "
            f"Total: ${order.total_amount}, Status: {order.status}"
        )

    except Exception as e:
        logger.error(
            f"❌ Error in handle_checkout_session_completed for Session ID {session_id}: {e}",
            exc_info=True
        )


# ==========================================================
# 2. MAIN WEBHOOK LISTENER
# ==========================================================

@router.post("/stripe-webhook", summary="Stripe Webhook Listener")
async def stripe_webhook_listener(
        request: Request,
        background_tasks: BackgroundTasks,
        user_manager: UserManager = Depends(get_user_manager)
):
    """
    Main Stripe webhook endpoint that handles events from both:
    - Platform account (account updates, etc.)
    - Connected accounts (checkout sessions, payments, etc.)
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    if not sig_header:
        raise HTTPException(status_code=400, detail="Stripe-Signature header missing")

    # ✅ Get the connected account ID from headers (if event is from connected account)
    stripe_account_id = request.headers.get('stripe-account')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )
    except Exception as e:
        logger.error(f"Webhook Error: Verification failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid webhook signature or payload")

    # Log event details
    event_type = event['type']
    object_id = event['data']['object'].id

    if stripe_account_id:
        logger.info(
            f"Received Stripe event: {event_type} for object ID: {object_id} "
            f"from connected account: {stripe_account_id}"
        )
    else:
        logger.info(f"Received Stripe event: {event_type} for object ID: {object_id}")

    # ==========================================================
    # EVENT ROUTING
    # ==========================================================

    # --- Handle Connect Account Updates (Platform Events) ---
    if event_type == 'account.updated':
        account = event['data']['object']
        connect_id = account.id

        background_tasks.add_task(
            handle_connect_account_update,
            user_manager,
            connect_id,
            account.get('charges_enabled', False),
            account.get('payouts_enabled', False)
        )

    # ✅ --- Handle Checkout Session Completion (Connected Account Events) ---
    elif event_type == 'checkout.session.completed':
        session = event['data']['object']
        session_id = session.id

        background_tasks.add_task(
            handle_checkout_session_completed,
            session_id,
            stripe_account_id  # Pass the connected account ID
        )

    # ✅ --- Handle Payment Intent Success (Optional - for additional tracking) ---
    elif event_type == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        logger.info(
            f"💰 Payment succeeded: {payment_intent.id} "
            f"Amount: ${payment_intent.amount / 100} {payment_intent.currency.upper()}"
        )
        # You can add additional handling here if needed

    # ✅ --- Handle Payment Intent Failure (Optional - for error tracking) ---
    elif event_type == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        logger.warning(
            f"❌ Payment failed: {payment_intent.id} "
            f"Error: {payment_intent.last_payment_error.get('message', 'Unknown error')}"
        )
        # You can add additional handling here (e.g., notify user, update order status)

    # --- Placeholder for Future Handlers ---
    # elif event_type == 'invoice.finalized':
    #     background_tasks.add_task(handle_invoice_finalized, ...)

    # elif event_type == 'customer.subscription.created':
    #     background_tasks.add_task(handle_subscription_created, ...)

    # --- Log unhandled events (for debugging) ---
    else:
        logger.info(f"ℹ️ Unhandled event type: {event_type}")

    # Final success response
    return {
        "status": "success",
        "received_event_type": event_type,
        "object_id": object_id,
        "from_connected_account": bool(stripe_account_id)
    }