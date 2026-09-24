"""Supabase 연결을 한곳에서 생성한다.

환경변수가 없는 개발자도 계산 로직과 단위 테스트를 실행할 수 있도록 앱 import
시점에는 연결하지 않는다. DB를 실제로 사용하는 요청에서만 설정을 검사한다.
"""

from functools import lru_cache
import os
from typing import Any

from dotenv import load_dotenv


load_dotenv()


@lru_cache(maxsize=1)
def get_supabase_client() -> Any:
    """백엔드 전용 Service Role 클라이언트를 반환한다."""

    url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_role_key:
        raise RuntimeError(
            "SUPABASE_URL과 SUPABASE_SERVICE_ROLE_KEY 환경변수가 필요합니다"
        )

    # 패키지가 없는 경우에도 앱의 비DB 기능은 import할 수 있어야 한다.
    from supabase import create_client

    return create_client(url, service_role_key)


if __name__ == "__main__":
    response = get_supabase_client().table("users").select("id").limit(1).execute()
    print("Supabase 연결 성공:", len(response.data), "건 확인")
