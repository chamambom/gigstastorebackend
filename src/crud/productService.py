from datetime import datetime
from typing import List, Optional
from beanie import PydanticObjectId
from src.models.productModel import Product, ProductStatus
from src.schemas.productSchema import ProductCreate, ProductUpdate


class ProductService:
    """Service layer for product operations"""

    @staticmethod
    async def create_product(
            seller_id: PydanticObjectId,
            product_data: ProductCreate
    ) -> Product:
        """Create a new product"""
        product = Product(
            seller_id=seller_id,
            **product_data.model_dump(),
            status=ProductStatus.DRAFT  # Products start as draft
        )
        await product.insert()
        return product

    @staticmethod
    async def get_user_products(
            user_id: PydanticObjectId,
            status_filter: Optional[str] = None
    ) -> List[Product]:
        """Get all products created by a user"""
        query = {"seller_id": user_id}

        if status_filter:
            query["status"] = status_filter

        # FIX: Beanie sort() expects tuple (field, direction)
        # -1 for descending, 1 for ascending

        products = await Product.find(query).sort(("created_at", -1)).to_list()
        return products

    @staticmethod
    async def list_published_products(
            category: Optional[str] = None,
            skip: int = 0,
            limit: int = 20
    ) -> List[Product]:
        """Get all published products with optional category filter"""
        query = {"status": ProductStatus.PUBLISHED}

        if category:
            query["category"] = category

        products = await (
            Product.find(query)
            .sort(("created_at", -1))
            .skip(skip)
            .limit(limit)
            .to_list()
        )
        return products

    @staticmethod
    async def list_published_products_with_seller(
            category: Optional[str] = None,
            skip: int = 0,
            limit: int = 20
    ) -> List[dict]:
        """Get all published products with seller information"""
        from src.models.userModel import User

        query = {"status": ProductStatus.PUBLISHED}

        if category:
            query["category"] = category

        # Fetch published products
        products = await (
            Product.find(query)
            .sort(("created_at", -1))
            .skip(skip)
            .limit(limit)
            .to_list()
        )

        # Fetch seller info for each product
        result = []
        for product in products:
            seller = await User.get(product.seller_id)

            product_dict = product.model_dump()

            if seller:
                product_dict["seller"] = {
                    "_id": str(seller.id),
                    "tradingName": seller.tradingName or "Unknown Seller",
                    "address": {
                        "city": seller.address.city if seller.address else None,
                        "locality": seller.address.locality if seller.address else None,
                    } if seller.address else None,
                    "overallProviderRating": seller.overallProviderRating,
                    "totalProviderReviews": seller.totalProviderReviews,
                }

            result.append(product_dict)

        return result

    @staticmethod
    async def update_product(
            product_id: PydanticObjectId,
            user_id: PydanticObjectId,
            product_data: ProductUpdate
    ) -> Product:
        """Update a product (owner only)"""
        product = await Product.get(product_id)

        if not product:
            raise ValueError("Product not found")

        if product.seller_id != user_id:
            raise PermissionError("You can only edit your own products")

        # Update only provided fields
        update_data = product_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(product, field, value)

        product.updated_at = datetime.utcnow()
        await product.save()

        return product

    @staticmethod
    async def delete_product(
            product_id: PydanticObjectId,
            user_id: PydanticObjectId
    ) -> None:
        """Delete a product (owner only)"""
        product = await Product.get(product_id)

        if not product:
            raise ValueError("Product not found")

        if product.seller_id != user_id:
            raise PermissionError("You can only delete your own products")

        await product.delete()

    @staticmethod
    async def publish_product(
            product_id: PydanticObjectId,
            user_id: PydanticObjectId
    ) -> Product:
        """Publish a product (make it available for purchase)"""
        product = await Product.get(product_id)

        if not product:
            raise ValueError("Product not found")

        if product.seller_id != user_id:
            raise PermissionError("You can only publish your own products")

        product.status = ProductStatus.PUBLISHED
        product.updated_at = datetime.utcnow()
        await product.save()

        return product

    @staticmethod
    async def archive_product(
            product_id: PydanticObjectId,
            user_id: PydanticObjectId
    ) -> Product:
        """Archive a product (remove from public listing)"""
        product = await Product.get(product_id)

        if not product:
            raise ValueError("Product not found")

        if product.seller_id != user_id:
            raise PermissionError("You can only archive your own products")

        product.status = ProductStatus.ARCHIVED
        product.updated_at = datetime.utcnow()
        await product.save()

        return product

    @staticmethod
    async def get_product_by_id(product_id: PydanticObjectId) -> Optional[Product]:
        """Get a single product by ID"""
        return await Product.get(product_id)