from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/ping")
def admin_ping():
    return {"message": "admin 라우터 살아있음"}