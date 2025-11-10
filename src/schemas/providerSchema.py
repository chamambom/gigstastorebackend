from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# class ProviderOverallStatsOut(BaseModel): provider_id: str = Field(..., description="The unique ID of the
# provider.") overallProviderRating: Optional[float] = Field(None, description="The overall average rating of the
# provider based on all their reviews.") totalProviderReviews: Optional[int] = Field(None, description="The total
# number of reviews for the provider.")
#
#     class Config:
#         # Pydantic v2 recommendation for converting BSON ObjectId to str
#         from_attributes = True  # Allows Pydantic to map fields by attribute names (useful with ORMs/ODMs)
#         json_encoders = {
#             # Beanie (Pydantic V2) typically handles ObjectId by default with from_attributes=True,
#             # but explicit encoder can be a fallback or for custom types.
#             # However, for ObjectId, relying on from_attributes=True or direct
#             # conversion in the query/CRUD is usually better.
#         }


class RatingInfo(BaseModel):
    average_service_rating: Optional[float] = None
    average_provider_rating: Optional[float] = None
    total_reviews: Optional[int] = 0  # Default to 0 if no reviews


class ServiceResponse(BaseModel):
    id: str
    service_category: Optional[str] = None
    service_description: str
    sub_category: Optional[str] = None
    created_at: datetime
    provider_id: str
    provider_name: Optional[str]
    provider_location: Optional[str]
    region: Optional[str]
    locality: Optional[str]
    ratings: RatingInfo


class RegionCountResponse(BaseModel):
    region: str
    locality: Optional[str] = None
    service_count: int


# NEW: Schema for subcategory service counts
class SubCategoryCountResponse(BaseModel):
    sub_category_name: str
    service_count: int


class PaginatedServiceResponse(BaseModel):
    total: int
    page: int
    page_size: int
    services: List[ServiceResponse]


class CombinedServiceResponse(BaseModel):
    filtered_services: PaginatedServiceResponse
    service_counts_by_region: List[RegionCountResponse]
    # NEW: Add an optional list of subcategory counts
    service_counts_by_subcategory: Optional[List[SubCategoryCountResponse]] = None


# class CombinedServiceResponse(BaseModel):
#     filtered_services: PaginatedServiceResponse
#     service_counts_by_region: List[RegionCountResponse]


############################################################################################

"""
Pydantic schemas for provider approval/rejection
Use these if you want to pass rejection reason in request body
"""


class ProviderRejectionRequest(BaseModel):
    """Request body for rejecting a provider"""
    rejection_reason: Optional[str] = Field(
        None,
        description="Reason for rejection (shown to provider in email)",
        max_length=500,
        example="Incomplete credentials or documentation"
    )


class ProviderApprovalResponse(BaseModel):
    """Response model for provider approval"""
    msg: str = Field(..., example="Provider user@example.com approved")
    provider_id: str = Field(..., example="507f1f77bcf86cd799439011")
    status: str = Field(..., example="approved")
    email_sent: bool = Field(default=True, example=True)


class ProviderRejectionResponse(BaseModel):
    """Response model for provider rejection"""
    msg: str = Field(..., example="Provider user@example.com rejected")
    provider_id: str = Field(..., example="507f1f77bcf86cd799439011")
    status: str = Field(..., example="rejected")
    rejection_reason: Optional[str] = Field(None, example="Incomplete documentation")
    email_sent: bool = Field(default=True, example=True)


class ResendNotificationResponse(BaseModel):
    """Response model for resending notification"""
    msg: str = Field(..., example="Approval notification resent")
    status: str = Field(..., example="approved")
