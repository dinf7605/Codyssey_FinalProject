from fastapi import APIRouter

# prefix: 이 부서의 주소는 전부 /auth 로 시작
# tags: /docs 에서 "auth" 그룹으로 묶어줌
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/ping")
def auth_ping():
    return {"message": "auth 라우터 살아있음"}