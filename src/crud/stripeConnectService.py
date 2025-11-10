# Assuming a new file: src/crud/stripeConnectService.py
from typing import Optional

from src.config.settings import settings
import stripe  # Assume you have the stripe library imported and configured


class StripeConnectService:

    def __init__(self):
        """
        Initializes the Stripe API key using the platform's secret key.
        This key is used for all API calls on behalf of the platform.
        """
        self.api_key = settings.stripe_keys["secret_key"]
        # Set the global API key once, or use it via 'stripe_account' header
        # on every call (as you are already doing). Setting it here is common practice.
        stripe.api_key = self.api_key

    # ------------------------------------------------------------------------------------------------------#
    #                                  create_connected_product_and_price                                   #
    # ------------------------------------------------------------------------------------------------------#

    async def create_connected_product_and_price(
            self,
            connected_account_id: str,
            title: str,
            description: str,
            price_in_cents: int,  # Stripe uses cents/lowest unit
            category: str,
            is_recurring: bool,
            interval: Optional[str] = None,
    ) -> dict:
        """
        Creates a Stripe Product and associated Price on a Connected Account.
        Supports both one-time and recurring products.
        """
        try:
            # ✅ Validate recurring logic FIRST
            if is_recurring and not interval:
                raise ValueError("Interval is required for recurring products.")

            # ✅ Ensure interval is None for one-time products
            if not is_recurring:
                interval = None

            # 1. Create Stripe Product on Connected Account
            stripe_product = stripe.Product.create(
                name=title,
                description=description,
                metadata={
                    "gigstastore_product_category": category,
                    "is_recurring": str(is_recurring).lower(),
                },
                # Crucial: Use the Stripe-Account header
                stripe_account=connected_account_id,
            )

            # 2. Setup Price parameters dynamically
            price_params = {
                "unit_amount": price_in_cents,
                "currency": "nzd",
                "product": stripe_product.id,
                "stripe_account": connected_account_id,
            }

            # ✅ Only add recurring if is_recurring is True
            if is_recurring and interval:
                price_params["recurring"] = {"interval": interval}

            # 3. Create the Stripe Price
            stripe_price = stripe.Price.create(**price_params)

            return {
                "product_id": stripe_product.id,
                "price_id": stripe_price.id,
            }

        except stripe.error.StripeError as e:
            print(f"Stripe Error: {e}")
            raise Exception(f"Failed to create Stripe resources: {e}")
        except Exception as e:
            print(f"General Error: {e}")
            raise Exception("An unexpected error occurred during Stripe integration.")

    # ------------------------------------------------------------------------------------------------------#
    #                                  update_connected_product_and_price                                   #
    # ------------------------------------------------------------------------------------------------------#

    async def update_connected_product_and_price(
            self,
            connected_account_id: str,
            stripe_product_id: str,
            stripe_price_id: str,
            title: str,
            description: str,
            price_in_cents: int,
            is_recurring: bool = False,
            interval: Optional[str] = None,
            update_price: bool = False  # ✅ NEW: Only create new price if True
    ) -> str:
        """
        Updates the Stripe Product and optionally creates a new Price.
        Returns the price ID (new if created, existing if not updated).
        """
        try:
            # 1. Always update the product metadata (safe, doesn't create duplicates)
            stripe.Product.modify(
                stripe_product_id,
                name=title,
                description=description,
                stripe_account=connected_account_id,
            )

            # 2. ✅ ONLY create new price if explicitly requested
            if update_price:
                # Archive the old price
                stripe.Price.modify(
                    stripe_price_id,
                    active=False,
                    stripe_account=connected_account_id,
                )

                # Create new price with updated values
                price_params = {
                    "unit_amount": price_in_cents,
                    "currency": "nzd",  # ✅ Fixed from "usd"
                    "product": stripe_product_id,
                    "stripe_account": connected_account_id,
                }

                # ✅ Add recurring only if applicable
                if is_recurring and interval:
                    price_params["recurring"] = {"interval": interval}

                new_stripe_price = stripe.Price.create(**price_params)
                return new_stripe_price.id

            # ✅ Return existing price ID if no update needed
            return stripe_price_id

        except stripe.error.StripeError as e:
            print(f"Stripe Update Error: {e}")
            raise Exception(f"Failed to update Stripe resources: {e}")

    # ------------------------------------------------------------------------------------------------------#
    #                                  deactivate_connected_product                                   #
    # ------------------------------------------------------------------------------------------------------#

    async def deactivate_connected_product(
            self,
            connected_account_id: str,
            stripe_product_id: str,
    ) -> None:
        """Deactivates the Stripe Product object."""
        try:
            stripe.Product.modify(
                stripe_product_id,
                active=False,
                stripe_account=connected_account_id,
            )
        except stripe.error.InvalidRequestError as e:
            # Handle case where the product might already be deleted or not exist
            if 'No such product' in str(e):
                print(f"Stripe Product {stripe_product_id} already missing.")
                return
            raise Exception(f"Failed to deactivate Stripe product: {e}")
        except stripe.error.StripeError as e:
            print(f"Stripe Deactivation Error: {e}")
            raise Exception(f"Failed to deactivate Stripe product: {e}")

    # ------------------------------------------------------------------------------------------------------#
    #                                  deactivate_connected_product                                         #
    # ------------------------------------------------------------------------------------------------------#

    async def create_checkout_session(
            self,
            customer_email: str,
            seller_stripe_account_id: str,
            stripe_price_id: str,
            success_url: str,
            cancel_url: str,
    ) -> str:
        """
        Creates a Stripe Checkout Session for a subscription or one-time purchase.

        Returns: The URL to redirect the customer to Stripe.
        """
        try:
            # Determine payment mode:
            # We check the Price object to see if it is recurring or one-time.
            price = stripe.Price.retrieve(
                stripe_price_id,
                stripe_account=seller_stripe_account_id
            )

            # The mode for the Checkout Session depends on the price type
            session_mode = 'subscription' if price.type == 'recurring' else 'payment'

            # 1. Prepare Line Item
            line_item = {
                'price': stripe_price_id,
                'quantity': 1,
            }

            # 2. Create the Session
            session = stripe.checkout.Session.create(
                # CRITICAL: Routes the payment/subscription to the SELLER
                stripe_account=seller_stripe_account_id,

                # Customer information
                customer_email=customer_email,

                # Setup URLs for redirection
                success_url=success_url,
                cancel_url=cancel_url,

                # Mode determines if it's a subscription or a simple charge
                mode=session_mode,

                # Add the price item
                line_items=[line_item],

                # Optional: For recurring, collecting the address is often required
                # if session_mode == 'subscription':
                #     session['billing_address_collection'] = 'required'
            )

            return session.url

        except stripe.error.StripeError as e:
            print(f"Stripe Session Creation Error: {e}")
            raise Exception(f"Failed to create Stripe Checkout Session: {e}")
