"""Supabase 연결을 한곳에서 생성한다.

연결을 얻는 방법이 두 가지다 (브랜치 통합 때 둘 다 살렸다).

  supabase / supabase_admin  — import 할 때 바로 연결한다.
                               인증·알림·설정(담당 E) 과 utils/auth.py 가 쓴다.
  get_supabase_client()      — 처음 부를 때 연결한다 (Service Role).
                               공모전 저장소(담당 D) 가 쓴다.

한 가지로 합칠지는 E·D 담당이 정한다. 합치기 전까지는 어느 쪽을 지워도 깨지는 곳이 있다.
"""

from functools import lru_cache
import os
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# 일반 클라이언트
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 관리자 클라이언트 (Auth 삭제용)
supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@lru_cache(maxsize=1)
def get_supabase_client() -> Any:
    """백엔드 전용 Service Role 클라이언트를 반환한다."""

    url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_role_key:
        raise RuntimeError(
            "SUPABASE_URL과 SUPABASE_SERVICE_ROLE_KEY 환경변수가 필요합니다"
        )

    return create_client(url, service_role_key)


# 연결 테스트용 (python db.py 로 직접 실행할 때만 작동)
if __name__ == "__main__":
    response = get_supabase_client().table("users").select("id").limit(1).execute()
    print("Supabase 연결 성공:", len(response.data), "건 확인")
