from typing import List, Dict, Any, Optional
from beanie import PydanticObjectId
from fastapi import HTTPException, status
import stripe
from datetime import datetime

from src.models.productModel import Product
from src.models.cartModel import Cart
from src.models.orderModel import Order, OrderStatus
from src.models.userModel import User
from src.crud.cartService import CartService


class CheckOutService:
    """Service layer for checkout operations with Stripe Connect"""

    # Platform fee percentage (e.g., 0.10 for 10%)
    PLATFORM_FEE_PERCENTAGE = 0.10

    @staticmethod
    def calculate_platform_fee(amount: float) -> tuple[float, float]:
        """
        Calculate platform fee and seller amount.

        Returns:
            tuple: (platform_fee_amount, seller_amount)
        """
        platform_fee = round(amount * CheckOutService.PLATFORM_FEE_PERCENTAGE, 2)
        seller_amount = round(amount - platform_fee, 2)
        return platform_fee, seller_amount

    @staticmethod
    async def create_checkout_session(
            user_id: PydanticObjectId,
            group: Dict[str, Any],
            success_url: str,
            cancel_url: str
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout Session for a single group (seller + payment type).

        Args:
            user_id: The buyer's user ID
            group: Cart group containing seller_id, items, is_recurring, etc.
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if user cancels

        Returns:
            Dict containing session info and order details
        """
        try:
            # 1. Fetch user to get stripe_customer_id
            user = await User.get(user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            # 2. Fetch seller to get stripe_connect_account_id
            seller_id = group["seller_id"]
            seller = await User.get(seller_id)
            if not seller or not seller.stripe_connect_account_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Seller has not completed Stripe onboarding"
                )

            # 3. Build line items for Stripe
            line_items = []
            cart_items = []
            total_amount = 0

            for item in group["items"]:
                product = item["product"]
                quantity = item["quantity"]

                # Validate product has Stripe IDs
                if not product.stripe_price_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Product '{product.title}' is missing Stripe price configuration"
                    )

                line_items.append({
                    "price": product.stripe_price_id,
                    "quantity": quantity,
                })

                # Track for order creation
                cart_items.append({
                    "product_id": product.id,
                    "quantity": quantity
                })

                total_amount += product.price * quantity

            # 4. Calculate fees
            platform_fee, seller_amount = CheckOutService.calculate_platform_fee(total_amount)

            # Convert platform fee to cents for Stripe
            platform_fee_cents = int(platform_fee * 100)

            # 5. Create Order record (pending state)
            order = Order(
                user_id=user_id,
                seller_id=seller_id,
                items=cart_items,
                total_amount=total_amount,
                platform_fee_amount=platform_fee,
                seller_amount=seller_amount,
                is_recurring=group["is_recurring"],
                status=OrderStatus.PENDING,
                stripe_account_id=seller.stripe_connect_account_id,
            )
            await order.insert()

            # 6. Add stripe_account parameter
            session_params = {
                "stripe_account": seller.stripe_connect_account_id,
                "mode": "subscription" if group["is_recurring"] else "payment",
                "line_items": line_items,
                "ui_mode": "embedded",
                "return_url": success_url,
                "metadata": {
                    "order_id": str(order.id),
                    "user_id": str(user_id),
                    "seller_id": str(seller_id),
                },
            }

            # 7. ✅ Handle customer differently for connected accounts
            # For connected accounts, you can either:
            # A) Pass customer email (Stripe creates new customer on connected account)
            # B) Create customer on connected account first, then reference it
            # Option A is simpler:
            if user.email:
                session_params["customer_email"] = user.email

            # 8. ✅ Handle platform fees for connected accounts
            if not group["is_recurring"]:
                # For one-time payments
                session_params["payment_intent_data"] = {
                    "application_fee_amount": platform_fee_cents,
                }
            else:
                # For subscriptions
                session_params["subscription_data"] = {
                    "application_fee_percent": CheckOutService.PLATFORM_FEE_PERCENTAGE * 100,
                }

            # 9. Create Stripe Checkout Session
            session = stripe.checkout.Session.create(**session_params)

            # 10. Update order with session ID
            order.stripe_checkout_session_id = session.id
            await order.save()

            return {
                "session_id": session.id,
                "client_secret": session.client_secret,  # For embedded checkout
                "order_id": str(order.id),
                "seller_name": group["seller_name"],
                "total_amount": total_amount,
                "platform_fee": platform_fee,
                "is_recurring": group["is_recurring"],
            }

        except stripe.error.StripeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stripe error: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Checkout error: {str(e)}"
            )

    @staticmethod
    async def create_all_checkout_sessions(
            user_id: PydanticObjectId,
            success_url: str,
            cancel_url: str
    ) -> List[Dict[str, Any]]:
        """
        Create checkout sessions for all groups in the cart.

        Returns:
            List of session details for each group
        """
        # Get grouped cart
        groups = await CartService.get_grouped_cart_for_checkout(user_id)

        if not groups:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cart is empty"
            )

        sessions = []
        for group in groups:
            session_info = await CheckOutService.create_checkout_session(
                user_id=user_id,
                group=group,
                success_url=success_url,
                cancel_url=cancel_url
            )
            sessions.append(session_info)

        return sessions

    @staticmethod
    async def handle_checkout_completion(session_id: str, stripe_account_id: str) -> Order:
        """
        Handle successful checkout completion (called by webhook).
        Updates order status and clears cart items.

        Args:
            session_id: Stripe checkout session ID
            stripe_account_id: The connected account ID (from webhook)

        Returns:
            Updated Order
        """
        # Find order by session ID
        order = await Order.find_one(Order.stripe_checkout_session_id == session_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        # ✅ Retrieve session from connected account
        session = stripe.checkout.Session.retrieve(
            session_id,
            stripe_account=stripe_account_id  # ✅ Important for connected accounts
        )

        # Update order
        order.status = OrderStatus.COMPLETED
        order.stripe_payment_intent_id = session.payment_intent
        order.completed_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        await order.save()

        # Clear completed items from cart
        cart = await Cart.find_one(Cart.user_id == order.user_id)
        if cart:
            # Remove items that were in this order
            order_product_ids = {item.product_id for item in order.items}
            cart.items = [
                item for item in cart.items
                if item.product_id not in order_product_ids
            ]
            await cart.save()

        return order

    @staticmethod
    async def get_order_by_id(order_id: PydanticObjectId) -> Optional[Order]:
        """Retrieve order by ID"""
        return await Order.get(order_id)

    @staticmethod
    async def get_user_orders(
            user_id: PydanticObjectId,
            limit: int = 50,
            skip: int = 0
    ) -> List[Order]:
        """Get all orders for a user"""
        orders = await Order.find(
            Order.user_id == user_id
        ).sort(-Order.created_at).skip(skip).limit(limit).to_list()
        return orders
