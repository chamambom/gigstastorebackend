# from contextlib import asynccontextmanager
# from typing import List, Annotated

# from beanie import init_beanie
# from pymongo.errors import PyMongoError
from fastapi import APIRouter, Depends, HTTPException, status
from src.config.settings import settings

# from app.db import User, db
from src.models.userModel import User
from src.schemas.userSchema import UserCreate, UserRead, UserUpdate, ProviderOnboarding, BasicUserCreate, \
    SetPasswordRequest
from src.crud.userService import (
    auth_backend,
    get_user_manager,
    current_active_user,
    fastapi_users,
    google_oauth_client,
    facebook_oauth_client,
    SECRET,
)
from fastapi_users.router.oauth import get_oauth_router

frontend_url = settings.FRONTEND_URL

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     await init_beanie(
#         database=db,
#         document_models=[
#             User,
#         ],
#     )
#     yield
#
#
# app = FastAPI(lifespan=lifespan)
#
router = APIRouter()

# Define authenticated routes
router.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

# ✅ OAuth router with frontend-based redirect (Option 2)
google_oauth_router = get_oauth_router(
    oauth_client=google_oauth_client,
    backend=auth_backend,
    get_user_manager=get_user_manager,
    redirect_url=f"{frontend_url}/google-oauth-callback",  # 👈 Must match Google Console
    state_secret=SECRET,
    associate_by_email=True  # ✅ this enables automatic linking
)
router.include_router(google_oauth_router, prefix="/auth/google", tags=["auth"])

facebook_oauth_router = get_oauth_router(
    oauth_client=facebook_oauth_client,
    backend=auth_backend,
    get_user_manager=get_user_manager,
    redirect_url=f"{frontend_url}/facebook-oauth-callback",  # 👈 This must match Facebook Developer settings
    state_secret=SECRET,
    associate_by_email=True
)

router.include_router(facebook_oauth_router, prefix="/auth/facebook", tags=["auth"])

# router.include_router(
#     fastapi_users.get_oauth_router(google_oauth_client, auth_backend, SECRET, associate_by_email=True),
#     prefix="/auth/google",
#     tags=["auth"],
# )
#
# router.include_router(
#     fastapi_users.get_oauth_associate_router(google_oauth_client, UserRead, SECRET),
#     prefix="/auth/associate/google",
#     tags=["auth"],
# )

# router.include_router(
#     fastapi_users.get_oauth_router(facebook_oauth_client, auth_backend, SECRET, associate_by_email=True),
#     prefix="/auth/facebook",
#     tags=["auth"],
# )

# @router.get("/authenticated-route")
# async def authenticated_route(user: User = Depends(current_active_user)):
#     return {"message": f"Hello {user.email}!"}
