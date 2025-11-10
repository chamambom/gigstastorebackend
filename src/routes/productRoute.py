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


# ============= PRODUCTS ROUTES =============
@router.post("/products", response_model=ProductRead, tags=["products"])
async def create_product(
        product_data: ProductCreate,
        current_user: User = Depends(current_active_user)
):
    """Create a new product (sellers only)"""
    # NOTE: current_user must have the 'stripe_connect_account_id' field accessible
    try:
        product = await ProductService.create_product(current_user.id, product_data)
        return product
    except ValueError as e:
        # This catches both the 'Stripe Connect account not linked' and the 'Stripe integration failed' errors
        error_detail = str(e)
        status_code = status.HTTP_400_BAD_REQUEST

        if "Stripe integration failed" in error_detail:
            # If the Stripe API call failed, treat it as a service error
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# @router.get("/products", response_model=List[ProductRead], tags=["products"])
# async def list_products(
#         category: str = None,
#         skip: int = 0,
#         limit: int = 20
# ):
#     """Get all published products with optional filtering"""
#     products = await ProductService.list_published_products(
#         category=category,
#         skip=skip,
#         limit=limit
#     )
#     return products


@router.get("/products", response_model=List[ProductRead], tags=["products"])
async def list_products(
        category: str = None,
        skip: int = 0,
        limit: int = 20
):
    """Get all published products with seller information"""
    products = await ProductService.list_published_products_with_seller(
        category=category,
        skip=skip,
        limit=limit
    )
    return products


@router.get("/products/{product_id}", response_model=ProductRead, tags=["products"])
async def get_product(product_id: PydanticObjectId):
    """Get a specific product"""
    product = await Product.get(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Allow viewing if published, or if user is the seller (checked in frontend/auth)
    # For now, only allow published products
    if product.status != "published":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Product is not available"
        )

    return product


@router.get("/products/user/my-products", response_model=List[ProductRead], tags=["products"])
async def get_my_products(
        current_user: User = Depends(current_active_user),
        status_filter: Optional[str] = None
):
    """Get all products created by current user"""
    products = await ProductService.get_user_products(current_user.id, status_filter)
    return products


@router.patch("/products/{product_id}", response_model=ProductRead, tags=["products"])
async def update_product(
        product_id: PydanticObjectId,
        product_data: ProductUpdate,
        current_user: User = Depends(current_active_user)
):
    """Update a product (owner only)"""
    try:
        product = await ProductService.update_product(
            product_id,
            current_user.id,
            product_data
        )
        return product
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own products"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete("/products/{product_id}", tags=["products"])
async def delete_product(
        product_id: PydanticObjectId,
        current_user: User = Depends(current_active_user)
):
    """Delete a product (owner only)"""
    try:
        await ProductService.delete_product(product_id, current_user.id)
        return {"message": "Product deleted successfully"}
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own products"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.patch("/products/{product_id}/publish", response_model=ProductRead, tags=["products"])
async def publish_product(
        product_id: PydanticObjectId,
        current_user: User = Depends(current_active_user)
):
    """Publish a product to make it available for purchase"""
    try:
        product = await ProductService.publish_product(product_id, current_user.id)
        return product
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only publish your own products"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.patch("/products/{product_id}/archive", response_model=ProductRead, tags=["products"])
async def archive_product(
        product_id: PydanticObjectId,
        current_user: User = Depends(current_active_user)
):
    """Archive a product (remove from public listing)"""
    try:
        product = await ProductService.archive_product(product_id, current_user.id)
        return product
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only archive your own products"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
