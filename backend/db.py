"""Supabase 연결 — 백엔드의 DB·인증 접근은 전부 여기를 거친다.

클라이언트는 두 가지다. 용도를 섞지 않는다.

  get_supabase_client()  서비스 키(Service Role). 테이블 읽기·쓰기, 토큰 확인, 관리자 작업(계정 삭제).
                         RLS 를 통과하므로 "본인 것만" 조건(.eq("user_id", user.id))을 코드에서 반드시 건다.
                         한 번 만들어 재사용한다.

  new_auth_client()      공개 키(anon). 가입·로그인 전용. 요청마다 새로 만든다.
                         로그인하면 클라이언트가 그 사용자의 세션을 품는다 — 공유 클라이언트로 로그인하면
                         그 뒤 다른 사람의 요청까지 마지막 로그인 사용자 권한으로 DB 를 조회하게 된다.

환경변수: SUPABASE_URL · SUPABASE_ANON_KEY · SUPABASE_SERVICE_ROLE_KEY
키가 없어도 앱은 뜬다. DB 를 쓰는 요청에서 DatabaseNotConfigured 가 나고, main.py 가 503 으로 바꾼다.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import config  # noqa: F401 - .env 를 먼저 읽는다


class DatabaseNotConfigured(RuntimeError):
    """Supabase 환경변수가 비어 있다."""


def _require(*names: str) -> list[str]:
    values = [os.getenv(n, "").strip() for n in names]
    missing = [n for n, v in zip(names, values) if not v]
    if missing:
        raise DatabaseNotConfigured(f"환경변수가 필요합니다: {', '.join(missing)}")
    return values


@lru_cache(maxsize=1)
def get_supabase_client() -> Any:
    """서비스 키 클라이언트 — 테이블·관리자 작업용. 절대 로그인에 쓰지 않는다."""
    url, key = _require("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
    from supabase import create_client

    return create_client(url, key)


def get_db() -> Any:
    """라우터용 의존성 — `db = Depends(get_db)`.

    테스트에서 app.dependency_overrides[get_db] 로 가짜 DB 를 끼울 수 있다 (tests/fake_supabase.py).
    """
    return get_supabase_client()


def new_auth_client() -> Any:
    """공개 키 클라이언트 — 가입·로그인 한 번에 하나씩 새로 만든다."""
    url, key = _require("SUPABASE_URL", "SUPABASE_ANON_KEY")
    from supabase import create_client

    return create_client(url, key)


# 연결 테스트용 (python db.py 로 직접 실행할 때만 작동)
if __name__ == "__main__":
    response = get_supabase_client().table("users").select("id").limit(1).execute()
    print("Supabase 연결 성공:", len(response.data), "건 확인")
