from fastapi import APIRouter

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("/ping")
def notifications_ping():
    return {"message": "notifications 라우터 살아있음"}