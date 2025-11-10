import boto3
from botocore.client import Config
from datetime import datetime
from fastapi import HTTPException, status
from typing import Literal
from beanie import PydanticObjectId
from pymongo import ReturnDocument

from src.schemas.productSchema import ProductRead, MediaFile
from src.models.productModel import Product
from src.schemas.userSchema import UserRead
from src.config.settings import settings

endpoint_url = settings.R2_ENDPOINT_URL
aws_access_key_id = settings.R2_ACCESS_KEY_ID
aws_secret_access_key = settings.R2_SECRET_ACCESS_KEY
cloud_flare_bucket = settings.R2_BUCKET
cloud_flare_r2_custom_domain = settings.R2_CUSTOM_DOMAIN

# Initialize R2 client
s3_client = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    # config=Config(signature_version="s3v4"),
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    region_name="auto",  # required by Cloudflare R2
)


async def generate_presigned_url(file_name: str, content_type: str):
    """Generate a raw presigned URL (not tied to a product)."""
    return s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": cloud_flare_bucket,
            "Key": file_name,
            "ContentType": content_type,
        },
        ExpiresIn=3600,  # 1 hour
    )


async def generate_presigned_upload(
        product_id: PydanticObjectId,
        file_name: str,
        file_type: Literal["image", "video"],
        file_size: int,
        content_type: str,
        current_user: UserRead,
):
    """Generate a presigned URL for uploading product media."""
    product = await Product.get(product_id)
    if not product or product.seller_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to upload media for this product.",
        )

    # --- New and Updated Business Rules ---
    MAX_IMAGES = 4
    MAX_VIDEOS = 2
    MAX_IMAGE_SIZE_KB = 500  # in KB
    MAX_VIDEO_SIZE_MB = 5  # in MB

    # Convert limits to bytes for comparison
    MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_KB * 1024
    MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024

    media = product.media or []
    images = [m for m in media if m.file_type == "image"]
    videos = [m for m in media if m.file_type == "video"]

    # Enforce per-file size and quantity limits
    if file_type == "image":
        if file_size > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image size cannot exceed {MAX_IMAGE_SIZE_KB}KB."
            )
        if len(images) >= MAX_IMAGES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You can only upload a maximum of {MAX_IMAGES} images per product."
            )
    elif file_type == "video":
        if file_size > MAX_VIDEO_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video size cannot exceed {MAX_VIDEO_SIZE_MB}MB."
            )
        if len(videos) >= MAX_VIDEOS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You can only upload a maximum of {MAX_VIDEOS} videos per product."
            )

    # Note: Your existing total size limit logic is good and should be kept.

    # generate unique object key
    object_key = f"products/{product_id}/{file_type}s/{datetime.utcnow().timestamp()}_{file_name}"

    # create presigned PUT URL
    presigned_url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": cloud_flare_bucket,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=3600,
    )

    # The fix to the URL path can be re-added here if needed.
    # corrected_upload_url = presigned_url.replace(f"/{cloud_flare_bucket}/", "/")

    return {
        "uploadUrl": presigned_url,
        "objectKey": object_key,
        "fileType": file_type,
        "fileSize": file_size,
    }


async def confirm_media_upload(
        product_id: PydanticObjectId,
        object_key: str,
        file_type: str,
        file_size: int,
        current_user: UserRead,
) -> ProductRead:
    """Confirm upload and persist media record in DB."""
    product = await Product.get(product_id)
    if not product or product.seller_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to update this product.",
        )

        # --- Change starts here ---
        # Construct the public URL using your custom domain
    # public_url_base = "https://media.gigsta.co.nz"
    # Ensure the URL is correctly formatted for web access
    # The `object_key` already contains the path like "product/..."
    # You might need to URL-encode the file name to handle spaces and special characters.
    import urllib.parse
    encoded_object_key = urllib.parse.quote(object_key, safe='/:')

    public_url = f"{cloud_flare_r2_custom_domain}/{encoded_object_key}"

    # --- Change ends here ---

    # append media to product
    media_file = MediaFile(
        url=public_url,
        # url=f"{endpoint_url}/{object_key}",
        object_key=object_key,
        file_type=file_type,
        size=file_size,
        uploaded_at=datetime.utcnow(),
    )

    if not product.media:
        product.media = []

    product.media.append(media_file)
    await product.save()

    return ProductRead.from_orm(product)


async def delete_product_media_crud(product_id: PydanticObjectId, object_key: str, current_user: UserRead):
    """Deletes media from Cloudflare R2 and the database."""

    # 1. Find the product and verify ownership
    product = await Product.get(product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    if product.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You are not authorized to delete media for this product.")

    # 2. Delete the file from Cloudflare R2
    try:
        s3_client.delete_object(
            Bucket=cloud_flare_bucket,
            Key=object_key
        )
    except Exception as e:
        # Log the error but proceed with database deletion for consistency
        print(f"Failed to delete object from R2: {e}")

    # 3. Delete the entry from the database using the object_key
    updated_product = await product.update(
        {"$pull": {"media": {"object_key": object_key}}}
    )

    if not updated_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found on product document.")

    return {"message": "Media deleted successfully."}
