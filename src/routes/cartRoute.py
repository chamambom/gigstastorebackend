from fastapi import APIRouter, Depends, HTTPException, status
from beanie import PydanticObjectId
from typing import List, Optional

from src.models.userModel import User
from src.models.productModel import Product
from src.schemas.productSchema import (
    ProductCreate, ProductUpdate, ProductRead,
    CartRead, CartAddItemRequest, CartUpdateItemRequest,
    ErrorResponse
)
from src.crud.userService import current_active_user
from src.crud.cartService import CartService
from src.crud.productService import ProductService

router = APIRouter()


# ============= CART ROUTES =============
@router.get("/cart", response_model=CartRead, tags=["cart"])
async def get_cart(current_user: User = Depends(current_active_user)):
    """Get current user's cart"""
    cart_data = await CartService.get_cart_with_products(current_user.id)
    return cart_data


@router.post("/cart/items", response_model=CartRead, tags=["cart"])
async def add_to_cart(
        item: CartAddItemRequest,
        current_user: User = Depends(current_active_user)
):
    """Add item to cart"""
    try:
        cart = await CartService.add_item(
            current_user.id,
            item.product_id,
            item.quantity
        )
        cart_data = await CartService.get_cart_with_products(current_user.id)
        return cart_data
    except HTTPException:
        raise


@router.patch("/cart/items/{product_id}", response_model=CartRead, tags=["cart"])
async def update_cart_item(
        product_id: PydanticObjectId,
        update: CartUpdateItemRequest,
        current_user: User = Depends(current_active_user)
):
    """Update quantity of item in cart"""
    try:
        cart = await CartService.update_item_quantity(
            current_user.id,
            product_id,
            update.quantity
        )
        cart_data = await CartService.get_cart_with_products(current_user.id)
        return cart_data
    except HTTPException:
        raise


@router.delete("/cart/items/{product_id}", response_model=CartRead, tags=["cart"])
async def remove_from_cart(
        product_id: PydanticObjectId,
        current_user: User = Depends(current_active_user)
):
    """Remove item from cart"""
    try:
        cart = await CartService.remove_item(current_user.id, product_id)
        cart_data = await CartService.get_cart_with_products(current_user.id)
        return cart_data
    except HTTPException:
        raise


@router.delete("/cart", response_model=CartRead, tags=["cart"])
async def clear_cart(current_user: User = Depends(current_active_user)):
    """Clear entire cart"""
    cart = await CartService.clear_cart(current_user.id)
    cart_data = await CartService.get_cart_with_products(current_user.id)
    return cart_data

