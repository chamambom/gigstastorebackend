from fastapi import APIRouter, Depends
from src.commonUtils.enumUtils import StripeProviderStatus
from src.models.userModel import User
from src.crud.userService import current_active_user

router = APIRouter()


@router.patch("/user/approve-provider")
async def approve_provider(user: User = Depends(current_active_user)):
    user.provider_status = StripeProviderStatus.ACTIVE
    await user.save()
    return {"msg": "Provider status set to approved"}
