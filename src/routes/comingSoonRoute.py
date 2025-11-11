from src.models.comingSoonModel import ComingSoonModel
from src.schemas.comingSoonSchema import ComingSoonForm
from fastapi import APIRouter

router = APIRouter()


@router.post("/coming-soon")
async def save_interest(data: ComingSoonForm):
    doc = ComingSoonModel(**data.dict())
    await doc.insert()
    return {"status": "ok"}
