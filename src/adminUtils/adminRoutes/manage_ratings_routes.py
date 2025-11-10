from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from beanie import PydanticObjectId
from src.schemas.ratingSchema import RatingInSchema, RatingOutSchema, UpdateRating
import src.crud.ratingCrud as Crud
from src.crud.userService import current_active_user

from src.models.userModel import User

router = APIRouter(tags=["Ratings"])


# Existing endpoints...
# Example:
@router.post("/ratings", response_model=RatingOutSchema, status_code=status.HTTP_201_CREATED)
async def create_new_rating(
        rating_data: RatingInSchema,
        current_user: User = Depends(current_active_user)
):
    return await Crud.create_rating(rating_data, current_user)


@router.put("/ratings/{rating_id}", response_model=RatingOutSchema)
async def update_existing_rating(
        rating_id: PydanticObjectId,
        rating_data: UpdateRating,
        current_user: User = Depends(current_active_user)
):
    return await Crud.update_rating(rating_id, rating_data, current_user)


@router.delete("/ratings/{rating_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_rating(
        rating_id: PydanticObjectId,
        current_user: User = Depends(current_active_user)
):
    await Crud.delete_rating(rating_id, current_user)
    return {"message": "Rating deleted successfully"}


# --- NEW ENDPOINT FOR MANUAL AGGREGATION (e.g., for Admin) ---
@router.post("/providers/{provider_id}/recalculate-ratings", status_code=status.HTTP_200_OK)
async def recalculate_provider_ratings_manually(
        provider_id: PydanticObjectId,
        current_user: User = Depends(current_active_user)  # Only allow admin or superuser
):
    # Optional: Add role-based access control here (e.g., if not current_user.is_superuser)
    if not current_user.is_superuser:  # Assuming only superusers can trigger this
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to perform this action.")

    try:
        await Crud.aggregate_and_update_provider_ratings(provider_id)
        return {"message": f"Ratings for provider {provider_id} recalculated successfully."}
    except Exception as e:
        Crud.logger.error(f"Error recalculating ratings for provider {provider_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to recalculate ratings: {e}")
