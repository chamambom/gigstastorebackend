import uvicorn as uvicorn
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis
import logging

from src.config.settings import settings
from src.config.database import startDB
from src.routes import r2CleanupRoute
from src.schedulers.r2_scheduler import r2_scheduler
from src.routes import userRoute, productRoute, cartRoute, addressableAPIRoute, userOnboardingRoute, \
    stripeSubscriptionServices, stripeWebhookHandler, mediaUploadRoute, checkOutRoute, comingSoonRoute
from src.adminUtils.adminRoutes import approveProviderRoute, admin_provider_routes, stripeAdministrationRoutes

# from src.adminUtils.adminRoutes import approveProviderRoute, admin_provider_routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def ip_whitelist_middleware(request: Request, call_next):
    try:
        # Skip IP check in production
        if settings.ENVIRONMENT.lower() == "production":
            logger.info(f"✅ Production mode - allowing {request.client.host}")
            return await call_next(request)

        allowed_ips = settings.allowed_ips

        # Skip if no IPs are configured (safety fallback)
        if not allowed_ips:
            logger.warning("⚠️ No ALLOWED_IPS set - allowing all requests")
            return await call_next(request)

        # Get client IP (with proxy support)
        client_ip = request.client.host
        if x_forwarded_for := request.headers.get("X-Forwarded-For"):
            client_ip = x_forwarded_for.split(",")[0].strip()

        logger.debug(f"Checking {client_ip} against allowed IPs: {allowed_ips}")

        if client_ip in allowed_ips:
            logger.info(f"✅ Allowed {client_ip} → {request.url}")
            return await call_next(request)
        else:
            logger.warning(f"⛔ Blocked {client_ip} (not in {allowed_ips})")
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Access forbidden",
                    "your_ip": client_ip,
                    "allowed_ips": allowed_ips
                }
            )

    except Exception as e:
        logger.error(f"IP check error: {str(e)}", exc_info=True)
        return await call_next(request)  # Safety fallthrough


# Initialize FastAPI app with lifespan context
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database connection and models (startup logic)
    await startDB()

    # Initialize rate limiter
    if settings.RATE_LIMITING_ENABLED:
        redis_connection = redis.from_url(settings.REDIS_URL, encoding="utf-8")
        await FastAPILimiter.init(redis_connection)

    # Start periodic R2 cleanup (only in production)
    # if settings.ENVIRONMENT.lower() == "production":
    #     r2_scheduler.start_periodic_cleanup()
    #     logger.info("R2 periodic cleanup enabled for production")
    # else:
    #     logger.info("R2 periodic cleanup disabled in non-production environment")

    yield

    # Shutdown logic (if any), for example, close resources
    # await client.close()

    # Shutdown logic
    # if settings.ENVIRONMENT.lower() == "production":
    #     r2_scheduler.stop_periodic_cleanup()


app = FastAPI(
    lifespan=lifespan,
    docs_url=None if settings.ENVIRONMENT.lower() == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT.lower() == "production" else "/redoc"
)

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler that formats all errors consistently"""
    error_response = {
        "error": {
            "type": exc.__class__.__name__,
            "message": "An error occurred",
            "detail": str(exc),
            "path": request.url.path,
        }
    }

    status_code = 500

    # Handle HTTP exceptions (404, 401, etc.)
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        error_response["error"]["message"] = exc.detail
        error_response["error"]["detail"] = exc.detail

    # Handle validation errors
    elif isinstance(exc, RequestValidationError):
        status_code = 422
        error_response["error"]["message"] = "Validation error"
        error_response["error"]["detail"] = exc.errors()

    # # --- ADD THIS NEW BLOCK ---
    # elif isinstance(exc, exceptions.InvalidPasswordException):
    #     status_code = 400
    #     error_response["error"]["message"] = "Invalid credentials"
    #     # Use the 'reason' from your custom exception as the detail
    #     error_response["error"]["detail"] = {"reason": exc.reason}
    #
    # # --- END NEW BLOCK ---

    # Log unexpected errors
    if status_code == 500:
        logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
        error_response["error"]["message"] = "Internal server error"
        # Don't expose internal details in production
        error_response["error"]["detail"] = "Please contact support"

    return JSONResponse(
        status_code=status_code,
        content=error_response
    )


# Register the handler for all exceptions
app.add_exception_handler(Exception, global_exception_handler)

# Add the IP whitelist middleware first
app.middleware("http")(ip_whitelist_middleware)

origins = settings.CLIENT_ORIGIN.split(",")  # Splits into ["http://localhost:81", "https://vercel-app.vercel.app"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(userRoute.router,
                   dependencies=[Depends(RateLimiter(times=100, seconds=60))])
# app.include_router(smartSearchRoute.router, tags=['location'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=100, seconds=60))])
# app.include_router(tagRoute.router, tags=['tag'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=100, seconds=60))])
# app.include_router(bookingRoute.router, tags=['bookings'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=100, seconds=60))])
# app.include_router(commissionPaymentRoute.router, tags=['commission-payments'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=100, seconds=60))])
app.include_router(productRoute.router, tags=['products'], prefix='/api/v1',
                   dependencies=[Depends(RateLimiter(times=100, seconds=60))]),
app.include_router(cartRoute.router, tags=['cart'], prefix='/api/v1',
                   dependencies=[Depends(RateLimiter(times=100, seconds=60))])
# app.include_router(categoryRoute.router, tags=['categories'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=100, seconds=60))])
# app.include_router(subCategoryRoute.router, tags=['subcategories'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=100, seconds=60))])
# app.include_router(ratingRoute.router, tags=['ratings'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=100, seconds=60))])
app.include_router(stripeWebhookHandler.router, tags=['StripeWebhook'], prefix='/api/v1',
                   dependencies=[Depends(RateLimiter(times=100, seconds=60))])
app.include_router(stripeSubscriptionServices.router, tags=['StripeSubs'], prefix='/api/v1',
                   dependencies=[Depends(RateLimiter(times=100, seconds=60))])
app.include_router(checkOutRoute.router, tags=['checkout'], prefix='/api/v1',
                   dependencies=[Depends(RateLimiter(times=100, seconds=60))])
# app.include_router(providerRoute.router, tags=['provider-checks'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=100, seconds=60))])
# app.include_router(providerAvailabilityRoute.router, tags=['provider-availability'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=100, seconds=60))])
app.include_router(mediaUploadRoute.router, tags=['UserMediaManagement'], prefix='/api/v1',
                   dependencies=[Depends(RateLimiter(times=100, seconds=60))])
app.include_router(addressableAPIRoute.router, tags=['3rdPartyAPIs'], prefix='/api/v1',
                   dependencies=[Depends(RateLimiter(times=10, seconds=60))]),
app.include_router(userOnboardingRoute.router, tags=['UserOnboarding'], prefix='/api/v1',
                   dependencies=[Depends(RateLimiter(times=5, seconds=60))])
app.include_router(admin_provider_routes.router, tags=['AdminUtils'], prefix='/api/v1/admin/providers',
                   dependencies=[Depends(RateLimiter(times=100, seconds=60))])
app.include_router(stripeAdministrationRoutes.router, tags=['StripeAdminUtils'], prefix='/api/v1/admin/stripe',
                   dependencies=[Depends(RateLimiter(times=100, seconds=60))])
app.include_router(comingSoonRoute.router, tags=['Coming Soon'], prefix='/api/v1',
                   dependencies=[Depends(RateLimiter(times=5, seconds=60))])
#
# app.include_router(newsletterRoute.router, tags=['NotificationRoute'], prefix='/api/v1',
#                    dependencies=[Depends(RateLimiter(times=5, seconds=60))])
#
app.include_router(r2CleanupRoute.router, tags=['r2-cleanup'], prefix='/api/v1/admin',
                   dependencies=[Depends(RateLimiter(times=5, seconds=60))])


# Example of rate-limited route
@app.get("/api/healthchecker", dependencies=[Depends(RateLimiter(times=100, seconds=60))])
def root():
    return {"message": "Welcome to GigSta"}


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=5001, reload=True, log_level="info")