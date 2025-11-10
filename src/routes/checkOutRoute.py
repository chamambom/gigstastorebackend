from fastapi import APIRouter, Depends, HTTPException, status
from beanie import PydanticObjectId
from typing import List

from src.models.userModel import User
from src.schemas.checkOutSchema import (
    CheckOutSessionRequest,
    CheckOutGroupResponse,
    OrderRead,
    GroupedCartResponse,
)
from src.crud.userService import current_active_user
from src.crud.checkOutService import CheckOutService
from src.crud.cartService import CartService
from src.crud.stripeConnectService import StripeConnectService


router = APIRouter()
stripe_service = StripeConnectService()


@router.get("/checkout/cart-preview",
            response_model=GroupedCartResponse,
            tags=["checkout"]
            )
async def get_grouped_cart(
        current_user: User = Depends(current_active_user)
):
    """
    Get cart grouped by seller and payment type for checkout preview.
    This shows the user how their cart will be split into multiple checkout sessions.
    """
    try:
        groups = await CartService.get_grouped_cart_for_checkout(current_user.id)

        grand_total = sum(group["group_total_price"] for group in groups)

        return {
            "groups": groups,
            "total_groups": len(groups),
            "grand_total": round(grand_total, 2)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving cart: {str(e)}"
        )


@router.post(
    "/checkout/create-sessions",
    response_model=CheckOutGroupResponse,
    tags=["checkout"]
)
async def create_checkout_sessions(
        request: CheckOutSessionRequest,
        current_user: User = Depends(current_active_user)
):
    """
    Create Stripe checkout sessions for all groups in the cart.
    Returns multiple session IDs and client secrets for embedded checkout.

    Each group (seller + payment type) gets its own checkout session.
    """
    try:
        sessions = await CheckOutService.create_all_checkout_sessions(
            user_id=current_user.id,
            success_url=str(request.success_url),
            cancel_url=str(request.cancel_url)
        )

        return {
            "sessions": sessions,
            "total_groups": len(sessions),
            "message": f"Created {len(sessions)} checkout session(s)"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating checkout sessions: {str(e)}"
        )


@router.get(
    "/orders",
    response_model=List[OrderRead],
    tags=["checkout", "orders"]
)
async def get_user_orders(
        limit: int = 50,
        skip: int = 0,
        current_user: User = Depends(current_active_user)
):
    """Get all orders for the current user"""
    try:
        orders = await CheckOutService.get_user_orders(
            user_id=current_user.id,
            limit=limit,
            skip=skip
        )
        return orders
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving orders: {str(e)}"
        )


@router.get(
    "/orders/{order_id}",
    response_model=OrderRead,
    tags=["checkout", "orders"]
)
async def get_order(
        order_id: PydanticObjectId,
        current_user: User = Depends(current_active_user)
):
    """Get a specific order by ID"""
    try:
        order = await CheckOutService.get_order_by_id(order_id)

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        # Ensure user owns this order
        if order.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this order"
            )

        return order
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving order: {str(e)}"
        )
