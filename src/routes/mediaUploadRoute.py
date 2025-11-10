from fastapi import APIRouter, Depends, Query, status
from beanie import PydanticObjectId
from typing import Literal

import src.crud.mediaUploadService as Crud
from src.crud.userService import current_active_user
from src.schemas.productSchema import ProductRead, MediaConfirmSchema  # Import the new schema
from src.schemas.userSchema import UserRead

router = APIRouter()


@router.post("/product/{product_id}/media/upload-request")
async def request_upload_url(
        product_id: PydanticObjectId,
        file_name: str = Query(...),  # Use Query to explicitly pull from URL params
        content_type: str = Query(...),  # Add the missing Content-Type parameter
        file_type: Literal["image", "video"] = Query(...),
        file_size: int = Query(...),
        current_user: UserRead = Depends(current_active_user)
):
    """
    Step 1: Get a presigned URL for upload.
    """
    return await Crud.generate_presigned_upload(product_id, file_name, file_type, file_size, content_type, current_user)


@router.post("/product/{product_id}/media/confirm", response_model=ProductRead)
async def confirm_upload(
        product_id: PydanticObjectId,
        media_data: MediaConfirmSchema,  # Use the Pydantic model to handle the JSON body
        current_user: UserRead = Depends(current_active_user)
) -> ProductRead:
    """
    Step 2: Confirm upload & save media reference in DB.
    """
    return await Crud.confirm_media_upload(
        product_id,
        media_data.object_key,
        media_data.file_type,
        media_data.file_size,
        current_user
    )


@router.delete("/product/{product_id}/media", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    product_id: PydanticObjectId,
    object_key: str = Query(...),  # Change this to accept a query parameter
    current_user: UserRead = Depends(current_active_user)
):
    """
    Deletes a specific media file from a product entry.
    """
    await Crud.delete_product_media_crud(product_id, object_key, current_user)
    return {"message": "Media deleted successfully."}