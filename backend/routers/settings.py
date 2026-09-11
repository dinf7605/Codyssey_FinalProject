from fastapi import APIRouter

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("/ping")
def settings_ping():
    return {"message": "settings 라우터 살아있음"}