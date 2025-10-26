from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from src.models.productModel import Product
from src.models.cartModel import Cart
from src.models.userModel import User
from src.models.stripeModel import StripeSubscriptions
from src.models.wishlistModel import Wishlist
from src.models.orderModel import Order
from .settings import settings


# Call this from within your event loop to get beanie setup.
async def startDB():
    # Create Motor client
    client = AsyncIOMotorClient(settings.MONGO_URI, uuidRepresentation="standard")
    database = client[settings.MONGO_DATABASE]

    # Init beanie with the Product document class
    await init_beanie(database=database,
                      document_models=[User, Product, Cart, StripeSubscriptions, Wishlist, Order
                                       # SubCategories, Categories, Ratings, ,
                                       # CommissionPayments, ProviderAvailability, Bookings, Newsletters
                                       ]
                      )

