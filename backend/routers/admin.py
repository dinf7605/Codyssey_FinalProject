from fastapi import APIRouter, Depends

from utils.admin import require_admin

# 앞으로 추가하는 관리자 API에도 권한 검사를 기본 적용한다.
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/ping")
def admin_ping():
    return {"message": "admin 라우터 살아있음"}


@router.get("/me")
def admin_me():
    """관리자 화면에서 접근 권한을 확인하는 API."""
    return {"is_admin": True}
