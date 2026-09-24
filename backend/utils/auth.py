from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from db import supabase

# 🔒 Bearer 토큰 보안 스킴
security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """토큰을 검사해서 유저 정보를 돌려주는 함수"""

    # credentials.credentials 에 이미 "Bearer" 뗀 순수 토큰이 들어있음!
    token = credentials.credentials

    # Supabase에게 토큰 검증 요청
    try:
        user_response = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")

    if not user_response or not user_response.user:
        raise HTTPException(status_code=401, detail="인증 실패")

    return user_response.user