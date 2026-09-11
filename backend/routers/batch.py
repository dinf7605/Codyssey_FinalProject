from fastapi import APIRouter

router = APIRouter(prefix="/batch", tags=["batch"])

@router.get("/ping")
def batch_ping():
    return {"message": "batch 라우터 살아있음"}