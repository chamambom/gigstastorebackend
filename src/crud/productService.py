from datetime import datetime
from typing import List, Optional
from beanie import PydanticObjectId
from src.models.productModel import Product, ProductStatus
from src.crud.stripeConnectService import StripeConnectService
from src.models.userModel import User
from src.schemas.productSchema import ProductCreate, ProductUpdate

# Instantiate the Stripe Service (Singleton for use in static methods)
# This will set stripe.api_key on initialization.
stripe_service = StripeConnectService()


class ProductService:
    """Service layer for product operations"""

    @staticmethod
    async def create_product(
            seller_id: PydanticObjectId,
            product_data: ProductCreate
    ) -> Product:
        """Create a new product locally and on Stripe Connected Account"""
        # 1. Fetch Seller's Connected Account ID
        seller = await User.get(seller_id)
        if not seller or not seller.stripe_connect_account_id:
            raise ValueError(
                "Seller's Stripe Connect account is not linked or active."
            )

        # ✅ Validate and normalize recurring fields
        if product_data.is_recurring:
            if not product_data.interval:
                raise ValueError("Interval is required for recurring products.")
        else:
            # ✅ Force interval to None for one-time products
            product_data.interval = None

        # 2. Create Product and Price on Stripe
        # Convert price to cents (Stripe's preferred format)
        price_in_cents = int(product_data.price * 100)

        # You'll need to define the subscription interval in your ProductCreate schema
        # or determine it here (e.g., product_data.interval)
        try:
            stripe_ids = await stripe_service.create_connected_product_and_price(
                connected_account_id=seller.stripe_connect_account_id,
                title=product_data.title,
                description=product_data.description,
                price_in_cents=price_in_cents,
                category=product_data.category,
                is_recurring=product_data.is_recurring,
                interval=product_data.interval,
            )
        except Exception as e:
            # Re-raise error to be caught in the API route
            raise ValueError(f"Stripe integration failed: {str(e)}")

        # 3. Create Product in Local DB with Stripe IDs
        product = Product(
            seller_id=seller_id,
            **product_data.model_dump(),
            status=ProductStatus.DRAFT,  # Products start as draft
            stripe_product_id=stripe_ids["product_id"],             # Save the new IDs
            stripe_price_id=stripe_ids["price_id"],
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
        """Update a product (owner only) and corresponding Stripe resources"""
        # 1. Get product and verify ownership
        product = await Product.get(product_id)
        if not product:
            raise ValueError("Product not found")

        if product.seller_id != user_id:
            raise PermissionError("You can only update your own products")

        # 2. Get seller info
        seller = await User.get(user_id)
        if not seller or not seller.stripe_connect_account_id:
            raise ValueError("Seller's Stripe Connect account is not available")

        # 3. Get update data
        update_data = product_data.model_dump(exclude_unset=True)

        # ✅ 4. Define which fields require Stripe updates
        stripe_product_fields = {'title', 'description'}  # These just update product metadata
        stripe_price_fields = {'price', 'is_recurring', 'interval'}  # These require new price

        fields_being_updated = set(update_data.keys())

        # Check what kind of Stripe update is needed
        needs_product_update = bool(stripe_product_fields & fields_being_updated)
        needs_price_update = bool(stripe_price_fields & fields_being_updated)

        # 5. Apply updates to local object first
        for field, value in update_data.items():
            setattr(product, field, value)

        # ✅ 6. Update Stripe only if relevant fields changed
        if (needs_product_update or needs_price_update) and product.stripe_product_id and product.stripe_price_id:
            try:
                price_in_cents = int(product.price * 100)

                # Call Stripe update with the update_price flag
                new_stripe_price_id = await stripe_service.update_connected_product_and_price(
                    connected_account_id=seller.stripe_connect_account_id,
                    stripe_product_id=product.stripe_product_id,
                    stripe_price_id=product.stripe_price_id,
                    title=product.title,
                    description=product.description,
                    price_in_cents=price_in_cents,
                    is_recurring=product.is_recurring,
                    interval=product.interval,
                    update_price=needs_price_update  # ✅ Only create new price if price fields changed
                )

                # Update price ID if a new one was created
                if new_stripe_price_id and new_stripe_price_id != product.stripe_price_id:
                    product.stripe_price_id = new_stripe_price_id

            except Exception as e:
                raise ValueError(f"Stripe update failed: {str(e)}")

        # 7. Save local changes
        product.updated_at = datetime.utcnow()
        await product.save()

        return product

    @staticmethod
    async def delete_product(
            product_id: PydanticObjectId,
            user_id: PydanticObjectId
    ) -> None:
        """Delete a product (owner only) and deactivate on Stripe"""
        product = await Product.get(product_id)
        if not product:
            raise ValueError("Product not found")

        if product.seller_id != user_id:
            raise PermissionError("You can only delete your own products")

        seller = await User.get(user_id)

        # 1. Deactivate on Stripe
        if product.stripe_product_id and seller and seller.stripe_connect_account_id:
            try:
                await stripe_service.deactivate_connected_product(
                    connected_account_id=seller.stripe_connect_account_id,
                    stripe_product_id=product.stripe_product_id
                )
            except Exception as e:
                print(f"Warning: Failed to deactivate Stripe product {product.stripe_product_id}: {str(e)}")

        # 2. Delete from Local DB
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

        # ✅ Validate product has Stripe resources before publishing
        if not product.stripe_product_id or not product.stripe_price_id:
            raise ValueError("Product must have associated Stripe resources before publishing")

        # ✅ Just update status - NO Stripe calls needed
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
