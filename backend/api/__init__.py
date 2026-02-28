from fastapi import APIRouter

from .routes import router as analyze_router


router = APIRouter()
router.include_router(analyze_router)

