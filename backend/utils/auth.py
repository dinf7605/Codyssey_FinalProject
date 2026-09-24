from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db import get_supabase_client

# 🔒 Bearer 토큰 보안 스킴
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """토큰을 검사해서 유저 정보를 돌려주는 함수.

    get_user(token) 은 토큰을 확인만 하고 클라이언트에 세션을 저장하지 않아서
    공유 클라이언트(서비스 키)로 불러도 다른 요청과 섞이지 않는다.
    """

    # credentials.credentials 에 이미 "Bearer" 뗀 순수 토큰이 들어있음!
    token = credentials.credentials

    # 설정이 비어 있으면 인증 실패가 아니라 서버 문제다 — 503 으로 나가게 try 밖에서 만든다
    db = get_supabase_client()

    # Supabase에게 토큰 검증 요청
    try:
        user_response = db.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")

    if not user_response or not user_response.user:
        raise HTTPException(status_code=401, detail="인증 실패")

    return user_response.user
