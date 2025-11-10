from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List, Optional
from beanie import PydanticObjectId
from src.models.userModel import User
from src.commonUtils.enumUtils import StripeProviderStatus
from src.crud.userService import current_active_user
from src.schemas.userSchema import UserRead  # Adjust to your public schema

from src.schemas.providerSchema import (
    ProviderRejectionRequest,
    ProviderApprovalResponse,
    ProviderRejectionResponse,
    ResendNotificationResponse
)
from src.commonUtils.email_renderer import (
    get_provider_approved_email,
    get_provider_rejected_email
)

from src.commonUtils.emailUtil import send_email
from src.config.settings import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# Ensure only superusers/admins can access
def require_admin(user: User = Depends(current_active_user)):
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return user


@router.patch("/approve/{user_id}", response_model=ProviderApprovalResponse)
async def approve_provider(
        user_id: PydanticObjectId,
        admin: User = Depends(require_admin)
):
    """
    Approve a provider application

    - **user_id**: The ID of the provider to approve
    - **Returns**: Approval confirmation with email status
    """
    provider = await User.get(user_id)

    if not provider:
        raise HTTPException(status_code=404, detail="User not found")

    if "provider" not in provider.roles:
        raise HTTPException(status_code=400, detail="User is not a provider")

    # Update provider status
    provider.provider_status = StripeProviderStatus.ACTIVE
    await provider.save()

    # Send approval email
    email_sent = True
    try:
        html_content = get_provider_approved_email(
            provider_email=provider.email,
            provider_name=provider.full_name,
            frontend_url=settings.FRONTEND_URL
        )

        await send_email(
            email=provider.email,
            subject=f"🎉 Your {settings.PLATFORM_NAME} Provider Application is Approved!",
            message=html_content
        )

        logger.info(f"✅ Provider approval email sent to {provider.email}")

    except Exception as e:
        logger.error(f"⚠️ Provider approved but email failed for {provider.email}: {e}")
        email_sent = False

    return ProviderApprovalResponse(
        msg=f"Provider {provider.email} approved",
        provider_id=str(provider.id),
        status="approved",
        email_sent=email_sent
    )


@router.patch("/reject/{user_id}", response_model=ProviderRejectionResponse)
async def reject_provider(
        user_id: PydanticObjectId,
        rejection_data: ProviderRejectionRequest = Body(...),  # Request body
        admin: User = Depends(require_admin)
):
    """
    Reject a provider application with optional reason

    - **user_id**: The ID of the provider to reject
    - **rejection_reason**: Optional reason for rejection (sent in email)
    - **Returns**: Rejection confirmation with email status

    Example request body:
    ```json
    {
        "rejection_reason": "Incomplete documentation or credentials"
    }
    ```
    """
    provider = await User.get(user_id)

    if not provider:
        raise HTTPException(status_code=404, detail="User not found")

    if "provider" not in provider.roles:
        raise HTTPException(status_code=400, detail="User is not a provider")

    # Update provider status
    provider.provider_status = StripeProviderStatus.REJECTED
    await provider.save()

    # Send rejection email with reason
    email_sent = True
    try:
        html_content = get_provider_rejected_email(
            provider_email=provider.email,
            provider_name=provider.full_name,
            rejection_reason=rejection_data.rejection_reason,
            frontend_url=settings.FRONTEND_URL
        )

        await send_email(
            email=provider.email,
            subject=f"Update on Your {settings.PLATFORM_NAME} Provider Application",
            message=html_content
        )

        logger.info(f"✅ Provider rejection email sent to {provider.email}")

    except Exception as e:
        logger.error(f"⚠️ Provider rejected but email failed for {provider.email}: {e}")
        email_sent = False

    return ProviderRejectionResponse(
        msg=f"Provider {provider.email} rejected",
        provider_id=str(provider.id),
        status="rejected",
        rejection_reason=rejection_data.rejection_reason,
        email_sent=email_sent
    )


@router.post("/resend-notification/{user_id}", response_model=ResendNotificationResponse)
async def resend_provider_notification(
        user_id: PydanticObjectId,
        admin: User = Depends(require_admin)
):
    """
    Resend the provider status notification email

    Useful if the original email failed or was not received by the provider

    - **user_id**: The ID of the provider
    - **Returns**: Confirmation that notification was resent
    """
    provider = await User.get(user_id)

    if not provider:
        raise HTTPException(status_code=404, detail="User not found")

    if "provider" not in provider.roles:
        raise HTTPException(status_code=400, detail="User is not a provider")

    try:
        if provider.provider_status == StripeProviderStatus.APPROVED:
            html_content = get_provider_approved_email(
                provider_email=provider.email,
                provider_name=provider.full_name,
                frontend_url=settings.FRONTEND_URL
            )

            await send_email(
                email=provider.email,
                subject=f"🎉 Your {settings.PLATFORM_NAME} Provider Application is Approved!",
                message=html_content
            )

            logger.info(f"✅ Resent provider approval email to {provider.email}")

            return ResendNotificationResponse(
                msg="Approval notification resent",
                status="approved"
            )

        elif provider.provider_status == StripeProviderStatus.REJECTED:
            html_content = get_provider_rejected_email(
                provider_email=provider.email,
                provider_name=provider.full_name,
                rejection_reason=None,
                frontend_url=settings.FRONTEND_URL
            )

            await send_email(
                email=provider.email,
                subject=f"Update on Your {settings.PLATFORM_NAME} Provider Application",
                message=html_content
            )

            logger.info(f"✅ Resent provider rejection email to {provider.email}")

            return ResendNotificationResponse(
                msg="Rejection notification resent",
                status="rejected"
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Provider status is {provider.provider_status}, cannot resend notification"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to resend notification to {provider.email}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resend notification: {str(e)}"
        )


@router.get("/", response_model=List[UserRead])  # Adjust schema
async def list_providers(status: StripeProviderStatus = StripeProviderStatus.ACTIVE, admin: User = Depends(require_admin)):
    providers = await User.find(
        {"roles": {"$in": ["provider"]}, "provider_status": status}
    ).to_list()
    return providers


@router.get("/{user_id}", response_model=UserRead)
async def get_provider(user_id: PydanticObjectId, admin: User = Depends(require_admin)):
    provider = await User.get(user_id)
    if not provider or "provider" not in provider.roles:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider
