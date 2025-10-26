import httpx
from fastapi import APIRouter, HTTPException, Query
from src.config.settings import settings

# Router instance
router = APIRouter()

ADDRESSABLE_API_KEY = settings.ADDRESSABLE_API_KEY


@router.get("/api/address/suggestions")
async def get_address_suggestions(
        query: str = Query(..., min_length=3, alias="q"),
        country_code: str = Query("NZ")
):
    if not ADDRESSABLE_API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.addressable.dev/v2/autocomplete",
                params={
                    "api_key": ADDRESSABLE_API_KEY,
                    "country_code": country_code,
                    "q": query,
                }
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Addressable API error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
