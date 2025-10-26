from typing import List
from beanie import PydanticObjectId
from fastapi import HTTPException, status
from src.models.productModel import Product
from src.models.cartModel import Cart, CartItem


class CartService:
    """Service layer for cart operations"""

    @staticmethod
    async def get_or_create_cart(user_id: PydanticObjectId) -> Cart:
        """Get existing cart or create new one"""
        cart = await Cart.find_one(Cart.user_id == user_id)

        if not cart:
            cart = Cart(user_id=user_id, items=[])
            await cart.insert()

        return cart

    @staticmethod
    async def add_item(user_id: PydanticObjectId, product_id: PydanticObjectId, quantity: int) -> Cart:
        """Add item to cart or increase quantity if exists"""
        # Verify product exists and seller can sell
        product = await Product.get(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        if product.status != "published":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product is not available for purchase"
            )

        cart = await CartService.get_or_create_cart(user_id)

        # Check if item already in cart
        existing_item = next(
            (item for item in cart.items if item.product_id == product_id),
            None
        )

        if existing_item:
            existing_item.quantity += quantity
        else:
            cart.items.append(CartItem(product_id=product_id, quantity=quantity))

        await cart.save()
        return cart

    @staticmethod
    async def remove_item(user_id: PydanticObjectId, product_id: PydanticObjectId) -> Cart:
        """Remove item from cart entirely"""
        cart = await CartService.get_or_create_cart(user_id)

        cart.items = [item for item in cart.items if item.product_id != product_id]

        await cart.save()
        return cart

    @staticmethod
    async def update_item_quantity(
            user_id: PydanticObjectId,
            product_id: PydanticObjectId,
            quantity: int
    ) -> Cart:
        """Update quantity of item in cart"""
        if quantity <= 0:
            return await CartService.remove_item(user_id, product_id)

        cart = await CartService.get_or_create_cart(user_id)

        item = next(
            (item for item in cart.items if item.product_id == product_id),
            None
        )

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item not in cart"
            )

        item.quantity = quantity
        await cart.save()
        return cart

    @staticmethod
    async def clear_cart(user_id: PydanticObjectId) -> Cart:
        """Clear all items from cart"""
        cart = await CartService.get_or_create_cart(user_id)
        cart.items = []
        await cart.save()
        return cart

    @staticmethod
    async def get_cart_with_products(user_id: PydanticObjectId) -> dict:
        """Get cart with full product details and calculations"""
        cart = await CartService.get_or_create_cart(user_id)

        # Fetch all products for items in cart
        product_ids = [item.product_id for item in cart.items]
        products = await Product.find({"_id": {"$in": product_ids}}).to_list()
        products_map = {p.id: p for p in products}

        # Build response with product details and calculations
        items_with_products = []
        total_price = 0
        total_items = 0

        for item in cart.items:
            product = products_map.get(item.product_id)

            if product and product.status == "published":
                item_total = product.price * item.quantity
                total_price += item_total
                total_items += item.quantity

                items_with_products.append({
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "product": product
                })

        return {
            "id": cart.id,
            "user_id": cart.user_id,
            "items": items_with_products,
            "total_items": total_items,
            "total_price": round(total_price, 2),
            "created_at": cart.created_at,
            "updated_at": cart.updated_at
        }