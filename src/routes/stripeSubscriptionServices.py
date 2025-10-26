from beanie import PydanticObjectId
from fastapi import APIRouter, Header, HTTPException, status, Response, Depends, Query
from typing import Optional, List

# from fastapi.logger import logger
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from src.commonUtils.emailUtil import send_email
# from src.config.celery_config import celery_app  # Import your Celery app
# from src.crud.stripeSubscriptionPaymentsCrud import get_all_subscriptions, get_user_subscription
from src.schemas.stripeSchema import StripeSubscriptionSchemaOut
from src.dependencies.subscription_dependencies import fetch_all_subscriptions

from src.config.settings import settings
from src.crud.userService import current_active_user
from src.schemas.userSchema import UserRead
from src.models.userModel import User
from src.models.productModel import Product
import stripe

from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

stripe.api_key = settings.stripe_keys["secret_key"]
solo_hustle_price_id = settings.stripe_keys["stripe_price_id_solo_hustle"]


# stripe.log = "debug"


@router.get('/config')
def get_publishable_key():
    stripe_config = {'publicKey': settings.stripe_keys['publishable_key']}
    return JSONResponse(stripe_config)


# ------------------------------------------------------------------------------------------------------#
#                                          Create Customer                                            #
# ------------------------------------------------------------------------------------------------------#
# @router.post("/create-stripe-customer")
# @celery_app.task
async def create_stripe_customer(
        email: str,
        user_id: str,  # Passed for Stripe metadata, not for DB update within this function
        full_name: str,
        address: dict,
) -> tuple[str, str]:  # This function will now return the customer_id and subscription_id
    """
    Creates a Stripe Customer and subscribes them to the Solo Hustle Free Plan.
    This function *only* interacts with the Stripe API and returns the necessary IDs.
    It does NOT update the User model in MongoDB or send emails.
    """
    try:
        # ✅ Create Stripe Customer
        customer = stripe.Customer.create(
            email=email,
            name=full_name,
            address={
                "line1": address.get("street", ""),
                "city": address.get("city", ""),
                "state": address.get("region", ""),
                "postal_code": address.get("postcode", ""),
                "country": "NZ"  # Adjust based on your region
            },
            metadata={"internal_user_id": user_id}  # Useful for linking Stripe customer to your user
        )
        print(f"✅ Stripe customer created: {customer.id}")

        # ✅ Create Subscription for Free Plan (Solo Hustle)
        # Ensure "price_1SFhdBLVP7ze9r9MvtopS2v4" is the correct Price ID for your free plan
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": solo_hustle_price_id}],
        )
        print(f"✅ Stripe subscription created: {subscription.id}")

        # --- REMOVED RESPONSIBILITIES ---
        # # ✅ Update User in MongoDB (THIS IS MOVED TO THE API ENDPOINT)
        # user = await User.get(user_id)
        # user.stripe_customer_id = customer.id
        # user.stripe_subscription_id = subscription.id
        # user.stripe_subscription_price_id = "price_1SFhdBLVP7ze9r9MvtopS2v4"
        # user.stripe_payment_method_id = ""
        # await user.save()
        # print(f"✅ User updated with Stripe details: {user.id}")

        # # ✅ Send Welcome Email (THIS IS MOVED TO THE API ENDPOINT)
        # subject = "Welcome to Solo Hustle!"
        # message = f""" ... """
        # await send_email(user.email, subject, message)
        # print(f"✅ Welcome email sent to {user.email}")
        # --- END REMOVED ---

        return customer.id, subscription.id

    except stripe.error.StripeError as e:
        print(f"❌ Stripe API error in create_stripe_customer: {e}")
        raise  # Re-raise the exception for the calling endpoint to handle
    except Exception as e:
        print(f"❌ Unexpected error in create_stripe_customer: {e}")
        raise  # Re-raise the exception for the calling endpoint to handle


# ------------------------------------------------------------------------------------------------------#
#                                          Create Payment Intent                                        #
# ------------------------------------------------------------------------------------------------------#

# The /api/create-payment-intent endpoint is supposed to connect to Stripe and create a PaymentIntent.
# It does not store payment intents in your local database. Instead, it should do the following:
#
# How create-payment-intent Works:
# Receives user_id and plan_id from the frontend
#
# user_id → Identifies the user making the payment.
# plan_id → The Stripe Price ID of the plan they are upgrading to.
# Fetches user details from the database
#
# Gets stripe_customer_id from the user’s record.
# Ensures the user exists and has a Stripe customer ID.
# Creates a PaymentIntent on Stripe
#
# Calls stripe.PaymentIntent.create() with the amount, currency, and stripe_customer_id.
# Returns a client_secret to the frontend.

# Request Model
class CreatePaymentIntentRequest(BaseModel):
    # user_id: str
    new_plan_id: str  # The Stripe Price ID


@router.post("/create-payment-intent")
async def create_payment_intent(
        data: CreatePaymentIntentRequest,
        subscriptions: List[StripeSubscriptionSchemaOut] = Depends(fetch_all_subscriptions),
        current_user: UserRead = Depends(current_active_user),  # Active user dependency
):
    # Fetch user from DB
    # user = await User.get(data.user_id)  # No need to fetch the user by ID since `user` is already

    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="User does not have a Stripe customer ID")

    # Find the selected plan in the subscriptions list
    selected_plan = next(
        (sub for sub in subscriptions if sub.stripe_price_id == data.new_plan_id), None
    )

    if not selected_plan:
        raise HTTPException(status_code=400, detail="Invalid plan selected")

    # Set plan price (assuming it's stored in the database)
    # plan_price = selected_plan.get("limit", 0) * 10  # Example pricing logic
    plan_price = 20

    try:
        # Create a PaymentIntent on Stripe
        payment_intent = stripe.PaymentIntent.create(
            amount=int(plan_price * 100),  # Convert to cents
            currency="nzd",
            customer=current_user.stripe_customer_id,
            payment_method_types=["card"],
        )

        return {"clientSecret": payment_intent.client_secret}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------------------------------------------#
#                                          Create Setup Intent                                          #
# ------------------------------------------------------------------------------------------------------#

@router.post("/create-setup-intent")
async def create_setup_intent(
        current_user: UserRead = Depends(current_active_user),
):
    stripe_customer_id = current_user.stripe_customer_id
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="User does not have a Stripe customer ID")

    try:
        # Create a Setup Intent
        setup_intent = stripe.SetupIntent.create(
            customer=stripe_customer_id,
            payment_method_types=["card"],
        )

        return {"clientSecret": setup_intent.client_secret}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------------------------------------------#
#                                          Save Card                                          #
# ------------------------------------------------------------------------------------------------------#
class AttachPaymentSubscriptionRequest(BaseModel):
    payment_method_id: str | None = None  # Optional if the user is adding a new payment method


@router.post("/save-card")
async def save_card(
        request: AttachPaymentSubscriptionRequest,  # Includes payment_method_id
        current_user: UserRead = Depends(current_active_user),
):
    stripe_customer_id = current_user.stripe_customer_id
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="User does not have a Stripe customer ID")

    try:
        # Check the number of saved payment methods
        saved_payment_methods = stripe.PaymentMethod.list(
            customer=stripe_customer_id,
            type="card"
        )
        if len(saved_payment_methods.data) >= 3:
            raise HTTPException(status_code=400, detail="You cannot add more than 3 payment methods.")

        # Attach the payment method to the customer
        stripe.PaymentMethod.attach(request.payment_method_id, customer=stripe_customer_id)

        # Set it as the default payment method
        stripe.Customer.modify(
            stripe_customer_id, invoice_settings={"default_payment_method": request.payment_method_id}
        )

        # Update in MongoDB
        current_user.stripe_payment_method_id = request.payment_method_id
        await current_user.save()

        return {"message": "Card saved and set as default successfully"}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------------------------------------------#
#                                          Get Payment Method                                           #
# ------------------------------------------------------------------------------------------------------#

@router.get("/get-payment-method")
async def get_payment_method(
        current_user: UserRead = Depends(current_active_user),
):
    stripe_customer_id = current_user.stripe_customer_id
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="User does not have a Stripe customer ID")

    try:
        # Retrieve the customer
        customer = stripe.Customer.retrieve(stripe_customer_id)

        # Get the default payment method
        default_payment_method_id = customer.invoice_settings.default_payment_method
        default_payment_method = None
        if default_payment_method_id:
            default_payment_method = stripe.PaymentMethod.retrieve(default_payment_method_id)

        # Get all saved payment methods
        saved_payment_methods = stripe.PaymentMethod.list(
            customer=stripe_customer_id,
            type="card"
        )

        # Format the response
        return {
            "has_payment_method": default_payment_method is not None,
            "default_payment_method": {
                "id": default_payment_method.id if default_payment_method else None,
                "brand": default_payment_method.card.brand if default_payment_method else None,
                "last4": default_payment_method.card.last4 if default_payment_method else None,
                "exp_month": default_payment_method.card.exp_month if default_payment_method else None,
                "exp_year": default_payment_method.card.exp_year if default_payment_method else None,
            },
            "saved_payment_methods": [
                {
                    "id": method.id,
                    "brand": method.card.brand,
                    "last4": method.card.last4,
                    "exp_month": method.card.exp_month,
                    "exp_year": method.card.exp_year,
                }
                for method in saved_payment_methods.data
            ]
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------------------------------------------#
#                                         Set Default Payment Method                                        #
# ------------------------------------------------------------------------------------------------------#

class SetDefaultPaymentMethodRequest(BaseModel):
    payment_method_id: str  # Required: The Stripe payment method ID to set as default


@router.post("/set-default-payment-method")
async def set_default_payment_method(
        request: SetDefaultPaymentMethodRequest,
        current_user: UserRead = Depends(current_active_user),
):
    stripe_customer_id = current_user.stripe_customer_id
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="User does not have a Stripe customer ID")

    if not request.payment_method_id:
        raise HTTPException(status_code=400, detail="Invalid payment method ID")

    try:
        # Set the payment method as default in Stripe
        stripe.Customer.modify(
            stripe_customer_id,
            invoice_settings={"default_payment_method": request.payment_method_id}
        )

        # Update the default payment method in MongoDB
        current_user.stripe_payment_method_id = request.payment_method_id
        await current_user.save()

        return {"message": "Default payment method updated successfully"}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------------------------------------------#
#                                          Attach Payment Method                                        #
# ------------------------------------------------------------------------------------------------------#
class AttachPaymentSubscriptionRequest(BaseModel):
    payment_method_id: str | None = None  # Optional if the user is adding a new payment method


@router.post("/attach-payment-method")
async def attach_payment_method(
        request: AttachPaymentSubscriptionRequest,  # Includes payment_method_id
        current_user: UserRead = Depends(current_active_user),
):
    stripe_customer_id = current_user.stripe_customer_id
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="User does not have a Stripe customer ID")

    try:
        # Attach payment method to the user
        stripe.PaymentMethod.attach(request.payment_method_id, customer=stripe_customer_id)

        # Set it as the default payment method
        stripe.Customer.modify(
            stripe_customer_id, invoice_settings={"default_payment_method": request.payment_method_id}
        )

        # Update in MongoDB
        current_user.stripe_payment_method_id = request.payment_method_id
        await current_user.save()

        return {"message": "Payment method attached successfully"}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------------------------------------------#
#                                          Upgrade Customer                                             #
# ------------------------------------------------------------------------------------------------------#
# # Define Stripe price IDs for each plan
# SUBSCRIPTION_PLANS = {
#     "solo": {"name": "Solo Hustle", "limit": 1, "stripe_price_id": "price_1QpdnqLVP7ze9r9MkZjEhkqZ"},
#     "pro": {"name": "Pro Hustle", "limit": 2, "stripe_price_id": "price_1QpdosLVP7ze9r9MkyrKLWsH"},
#     "elite": {"name": "Elite Hustle", "limit": 5, "stripe_price_id": "price_1QpdpnLVP7ze9r9Mwy62L8WF"},
# }

class UpgradeSubscriptionRequest(BaseModel):
    new_plan: str
    payment_method_id: str | None = None  # Optional if the user is adding a new payment method


@router.post("/upgrade-subscription")
async def upgrade_subscription(
        request: UpgradeSubscriptionRequest,
        subscriptions: List[StripeSubscriptionSchemaOut] = Depends(fetch_all_subscriptions),
        current_user: UserRead = Depends(current_active_user),
):
    try:
        # Fetch the Stripe customer ID linked to the user
        stripe_customer_id = current_user.stripe_customer_id
        if not stripe_customer_id:
            raise HTTPException(status_code=400, detail="User does not have a Stripe customer ID.")

        # ✅ Validate the new plan
        matching_subscription = next(
            (sub for sub in subscriptions if sub.stripe_price_id == request.new_plan), None
        )
        if not matching_subscription:
            raise HTTPException(status_code=400, detail="Invalid subscription plan")

        stripe_price_id = matching_subscription.stripe_price_id

        # # Attach the payment method to the customer (if not already)
        # stripe.PaymentMethod.attach(
        #     request.payment_method_id,
        #     customer=stripe_customer_id
        # )
        #
        # # Set default payment method for future invoices
        # stripe.Customer.modify(
        #     stripe_customer_id,
        #     invoice_settings={"default_payment_method": request.payment_method_id}
        # )

        # Get the user's current subscription
        subscriptions = stripe.Subscription.list(customer=stripe_customer_id, status="active")
        if not subscriptions.data:
            raise HTTPException(status_code=400, detail="No active subscription found.")

        current_subscription = subscriptions.data[0]

        # Update the subscription with new price ID
        updated_subscription = stripe.Subscription.modify(
            current_subscription.id,
            items=[{"id": current_subscription["items"]["data"][0].id, "price": stripe_price_id}],
            proration_behavior="create_prorations",
        )

        # ✅ Update MongoDB User Model
        # current_user.stripe_payment_method_id = payment_method_id
        current_user.stripe_subscription_id = updated_subscription.id
        current_user.stripe_subscription_price_id = stripe_price_id
        await current_user.save()

        return {"message": "Subscription upgraded successfully", "subscription": updated_subscription}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------------------------------------------#
#                                          Downgrade Customer                                             #
# ------------------------------------------------------------------------------------------------------#
# # Define Stripe price IDs for each plan
# SUBSCRIPTION_PLANS = {
#     "solo": {"name": "Solo Hustle", "limit": 1, "stripe_price_id": "price_1QpdnqLVP7ze9r9MkZjEhkqZ"},
#     "pro": {"name": "Pro Hustle", "limit": 2, "stripe_price_id": "price_1QpdosLVP7ze9r9MkyrKLWsH"},
#     "elite": {"name": "Elite Hustle", "limit": 5, "stripe_price_id": "price_1QpdpnLVP7ze9r9Mwy62L8WF"},
# }

class DowngradeSubscriptionRequest(BaseModel):
    new_plan: str
    payment_method_id: str | None = None  # Optional if the user is adding a new payment method


@router.post("/downgrade-subscription")
async def downgrade_subscription(
        request: DowngradeSubscriptionRequest,
        subscriptions: List[StripeSubscriptionSchemaOut] = Depends(fetch_all_subscriptions),
        current_user: UserRead = Depends(current_active_user),
):
    try:
        stripe_customer_id = current_user.stripe_customer_id
        if not stripe_customer_id:
            raise HTTPException(status_code=400, detail="User does not have a Stripe customer ID.")

        # Validate the new plan
        matching_subscription = next(
            (sub for sub in subscriptions if sub.stripe_price_id == request.new_plan), None
        )
        if not matching_subscription:
            raise HTTPException(status_code=400, detail="Invalid subscription plan")

        stripe_price_id = matching_subscription.stripe_price_id

        # Get the user's current subscription
        subscriptions = stripe.Subscription.list(customer=stripe_customer_id, status="active")
        if not subscriptions.data:
            raise HTTPException(status_code=400, detail="No active subscription found.")

        current_subscription = subscriptions.data[0]

        # Update the subscription with new price ID
        updated_subscription = stripe.Subscription.modify(
            current_subscription.id,
            items=[{"id": current_subscription["items"]["data"][0].id, "price": stripe_price_id}],
            proration_behavior="none",  # No proration for downgrades
        )

        # Update MongoDB User Model
        current_user.stripe_subscription_id = updated_subscription.id
        current_user.stripe_subscription_price_id = stripe_price_id
        await current_user.save()

        return {"message": "Subscription downgraded successfully", "subscription": updated_subscription}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------------------------------------------#
#                                         Cancel sub                                                    #
# ------------------------------------------------------------------------------------------------------#
# class DeleteStripePaymentMethodRequest(BaseModel):
#     payment_method_id: str | None = None  # Optional if the user is adding a new payment method


@router.delete("/delete-card/{payment_method_id}")
async def delete_card(
        payment_method_id: str,  # Extract ID from the URL path.
        current_user: UserRead = Depends(current_active_user),
):
    try:
        # Retrieve all the user's payment methods
        payment_methods = stripe.PaymentMethod.list(
            customer=current_user.stripe_customer_id, type="card"
        ).data

        # Check if the card being deleted is the default
        customer = stripe.Customer.retrieve(current_user.stripe_customer_id)
        current_default = customer.invoice_settings.default_payment_method

        # Delete the card
        stripe.PaymentMethod.detach(payment_method_id)

        # If the deleted card was the default, set a new default if another card exists
        if current_default == payment_method_id and payment_methods:
            new_default = next((pm.id for pm in payment_methods if pm.id != payment_method_id), None)

            if new_default:
                stripe.Customer.modify(
                    current_user.stripe_customer_id,
                    invoice_settings={"default_payment_method": new_default}
                )

        return {"message": "Payment method deleted successfully."}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------------------------------------------#
#                                         Upgrade and Downgrade Options                                 #
# ------------------------------------------------------------------------------------------------------#
def convert_subscription_to_dict(sub: StripeSubscriptionSchemaOut) -> dict:
    """Safely converts subscription to dict with proper _id handling"""
    data = sub.model_dump(by_alias=True)  # Ensures _id comes through
    data["_id"] = str(data["_id"])  # Explicitly convert ObjectId to string
    return data


@router.get("/subscription-options", response_model=dict)
async def get_subscription_options(
        current_user: UserRead = Depends(current_active_user),
        subscriptions: List[StripeSubscriptionSchemaOut] = Depends(fetch_all_subscriptions)
):
    user_price_id = current_user.stripe_subscription_price_id

    if not user_price_id:
        return {"error": "User has no active subscription."}

    current_subscription = next(
        (sub for sub in subscriptions if sub.stripe_price_id == user_price_id),
        None
    )

    if not current_subscription:
        return {"error": "Current subscription plan not found."}

    # Count user’s current services
    service_count = await Product.find(
        Product.seller_id == current_user.id
    ).count()

    # Build current plan info
    current_plan = convert_subscription_to_dict(current_subscription)
    current_plan.update({
        "services_used": service_count,
        "can_add_more": service_count < current_subscription.limit
    })

    # Upgrade = price > current
    upgrade_options = [
        convert_subscription_to_dict(sub)
        for sub in subscriptions
        if sub.plan_price > current_subscription.plan_price
    ]

    # Downgrade split: based on price and service count
    valid_downgrades = []
    blocked_downgrades = []

    for sub in subscriptions:
        if sub.plan_price < current_subscription.plan_price:
            sub_dict = convert_subscription_to_dict(sub)
            if service_count <= sub.limit:
                valid_downgrades.append(sub_dict)
            else:
                sub_dict["reason"] = f"Too many services ({service_count}/{sub.limit})"
                blocked_downgrades.append(sub_dict)

    return {
        "currentPlan": current_plan,
        "upgradeOptions": upgrade_options,
        "downgradeOptions": valid_downgrades,
        "blockedDowngradeOptions": blocked_downgrades
    }


# @router.get("/subscription-options", response_model=dict)
# async def get_subscription_options(
#         current_user: UserRead = Depends(current_active_user),
#         subscriptions: List[StripeSubscriptionSchemaOut] = Depends(fetch_all_subscriptions)
# ):
#     """
#     Get available upgrade and downgrade options for the logged-in user.
#     """
#
#     # Get the user's current subscription price ID
#     user_price_id = current_user.stripe_subscription_price_id
#
#     if not user_price_id:
#         return {"error": "User has no active subscription."}
#
#     # Find the user's current subscription plan
#     current_subscription = next(
#         (sub for sub in subscriptions if sub.stripe_price_id == user_price_id),
#         None
#     )
#
#     if not current_subscription:
#         return {"error": "Current subscription plan not found."}
#
#     # Determine upgrade and downgrade options based on price
#     upgrade_options = [sub for sub in subscriptions if sub.plan_price > current_subscription.plan_price]
#     downgrade_options = [sub for sub in subscriptions if sub.plan_price < current_subscription.plan_price]
#
#     return {
#         "currentPlan": current_subscription,
#         "upgradeOptions": upgrade_options,
#         "downgradeOptions": downgrade_options,
#     }


# ------------------------------------------------------------------------------------------------------#
#                                         Cancel sub                                                    #
# ------------------------------------------------------------------------------------------------------#


# Default free plan (Solo Hustle)
DEFAULT_PLAN = {
    "name": "Solo Hustle",
    "limit": 1,
    "stripe_price_id": None,  # No Stripe subscription for free plan
}


#
# @router.post("/cancel-subscription")
# async def cancel_subscription(user_id: str, downgrade_to_free: bool = True):
#     """
#     Cancels the user's Stripe subscription.
#     - If `downgrade_to_free=True`, the user is downgraded to Solo Hustle.
#     - If `downgrade_to_free=False`, the subscription details are removed.
#     """
#     # ✅ Step 1: Fetch user from MongoDB
#     user = await User.get(PydanticObjectId(user_id))
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found.")
#
#     if not user.stripe_subscription_id:
#         raise HTTPException(status_code=400, detail="User has no active Stripe subscription.")
#
#     # ✅ Step 2: Cancel the existing Stripe subscription
#     try:
#         stripe.Subscription.delete(user.stripe_subscription_id)
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Failed to cancel subscription: {str(e)}")
#
#     # ✅ Step 3: Update MongoDB
#     if downgrade_to_free:
#         # Downgrade to the free Solo Hustle plan
#         user.subscription_plan = DEFAULT_PLAN["name"]
#         user.service_limit = DEFAULT_PLAN["limit"]
#         user.stripe_subscription_id = ""
#     else:
#         # Remove subscription details
#         user.subscription_plan = None
#         user.service_limit = None
#         user.stripe_subscription_id = ""
#
#     await user.save()
#
#     return {
#         "message": "Subscription canceled successfully.",
#         "subscription_plan": user.subscription_plan,
#         "service_limit": user.service_limit,
#         "stripe_subscription_id": user.stripe_subscription_id,
#     }

# ------------------------------------------------------------------------------------------------------#
#                                         Get Invoices                                                  #
# ------------------------------------------------------------------------------------------------------#

# @router.get("/get-invoices")
# async def get_invoices(
#         current_user: UserRead = Depends(current_active_user),
#         limit: int = 10  # Optional parameter to limit number of invoices returned
# ):
#     stripe_customer_id = current_user.stripe_customer_id
#     if not stripe_customer_id:
#         raise HTTPException(status_code=400, detail="User does not have a Stripe customer ID")
#
#     try:
#         # Retrieve all invoices for the customer, sorted by most recent first
#         invoices = stripe.Invoice.list(
#             customer=stripe_customer_id,
#             limit=limit,
#             expand=['data.payment_intent']  # Expand payment intent to get more details
#         )
#
#         # Format the response
#         formatted_invoices = []
#         for invoice in invoices.data:
#             formatted_invoice = {
#                 "id": invoice.id,
#                 "number": invoice.number,
#                 "created": invoice.created,
#                 "status": invoice.status,
#                 "amount_due": invoice.amount_due,
#                 "amount_paid": invoice.amount_paid,
#                 "currency": invoice.currency.upper(),
#                 "pdf_url": invoice.invoice_pdf,
#                 "hosted_invoice_url": invoice.hosted_invoice_url,
#                 "period_start": invoice.period_start,
#                 "period_end": invoice.period_end,
#                 "lines": [
#                     {
#                         "amount": line.amount,
#                         "currency": line.currency.upper(),
#                         "description": line.description,
#                         "quantity": line.quantity,
#                     }
#                     for line in invoice.lines.data
#                 ]
#             }
#
#             # Add payment method details if available
#             if invoice.payment_intent and hasattr(invoice.payment_intent, 'payment_method'):
#                 payment_method = stripe.PaymentMethod.retrieve(invoice.payment_intent.payment_method)
#                 formatted_invoice["payment_method"] = {
#                     "brand": payment_method.card.brand if hasattr(payment_method, 'card') else None,
#                     "last4": payment_method.card.last4 if hasattr(payment_method, 'card') else None,
#                 }
#
#             formatted_invoices.append(formatted_invoice)
#
#         return {
#             "count": len(formatted_invoices),
#             "invoices": formatted_invoices
#         }
#     except stripe.error.StripeError as e:
#         raise HTTPException(status_code=400, detail=str(e))

@router.get("/get-invoices")
async def get_invoices(
        current_user: UserRead = Depends(current_active_user),
        limit: int = Query(10, ge=1, le=100, description="Number of invoices to return")
) -> Dict[str, Any]:
    """
    Retrieve Stripe invoices for the current user.

    Args:
        current_user: The authenticated user
        limit: Maximum number of invoices to return (1-100)

    Returns:
        Dictionary containing count and list of formatted invoices

    Raises:
        HTTPException: If user has no Stripe customer ID or Stripe API error occurs
    """
    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="User does not have a Stripe customer ID"
        )

    try:
        # Retrieve invoices with expanded payment intent data
        invoices = stripe.Invoice.list(
            customer=current_user.stripe_customer_id,
            limit=limit,
            expand=['data.payment_intent']
        )

        formatted_invoices = [
            await _format_invoice(invoice) for invoice in invoices.data
        ]

        return {
            "count": len(formatted_invoices),
            "invoices": formatted_invoices
        }

    except stripe.error.InvalidRequestError as e:
        logger.error(f"Invalid Stripe request for user {current_user.id}: {e}")
        raise HTTPException(status_code=400, detail="Invalid request to Stripe")

    except stripe.error.AuthenticationError as e:
        logger.error(f"Stripe authentication error: {e}")
        raise HTTPException(status_code=500, detail="Payment service authentication error")

    except stripe.error.RateLimitError as e:
        logger.error(f"Stripe rate limit exceeded: {e}")
        raise HTTPException(status_code=429, detail="Too many requests, please try again later")

    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Payment service error")


async def _format_invoice(invoice) -> Dict[str, Any]:
    """
    Format a Stripe invoice object into a standardized response format.

    Args:
        invoice: Stripe invoice object

    Returns:
        Formatted invoice dictionary
    """
    formatted_invoice = {
        "id": invoice.id,
        "number": invoice.number,
        "created": datetime.fromtimestamp(invoice.created).isoformat(),
        "status": invoice.status,
        "amount_due": invoice.amount_due,
        "amount_paid": invoice.amount_paid,
        "currency": invoice.currency.upper(),
        "pdf_url": invoice.invoice_pdf,
        "hosted_invoice_url": invoice.hosted_invoice_url,
        "period_start": datetime.fromtimestamp(invoice.period_start).isoformat() if invoice.period_start else None,
        "period_end": datetime.fromtimestamp(invoice.period_end).isoformat() if invoice.period_end else None,
        "lines": _format_invoice_lines(invoice.lines.data),
        "payment_method": None  # Default to None
    }

    # Only try to get payment method if payment_intent exists and has a payment_method
    if (invoice.payment_intent and
            hasattr(invoice.payment_intent, 'payment_method') and
            invoice.payment_intent.payment_method):

        try:
            payment_method = stripe.PaymentMethod.retrieve(
                invoice.payment_intent.payment_method
            )
            formatted_invoice["payment_method"] = _format_payment_method(payment_method)
        except stripe.error.StripeError as e:
            logger.warning(f"Could not retrieve payment method for invoice {invoice.id}: {e}")
            # Continue without payment method data

    return formatted_invoice


def _format_invoice_lines(lines: List) -> List[Dict[str, Any]]:
    """Format invoice line items."""
    return [
        {
            "amount": line.amount,
            "currency": line.currency.upper(),
            "description": line.description,
            "quantity": line.quantity,
        }
        for line in lines
    ]


def _format_payment_method(payment_method) -> Optional[Dict[str, Any]]:
    """
    Format payment method data safely.

    Args:
        payment_method: Stripe PaymentMethod object

    Returns:
        Formatted payment method dict or None if no card data
    """
    if hasattr(payment_method, 'card') and payment_method.card:
        return {
            "type": payment_method.type,
            "brand": payment_method.card.brand,
            "last4": payment_method.card.last4,
            "exp_month": payment_method.card.exp_month,
            "exp_year": payment_method.card.exp_year,
        }

    # Handle other payment method types (bank transfers, etc.)
    return {
        "type": payment_method.type,
        "brand": None,
        "last4": None,
    }

# ------------------------------------------------------------------------------------------------------#
#                                                                                                       #
# ------------------------------------------------------------------------------------------------------#
