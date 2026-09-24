"""Claude 호출 공통 — Codyssey 게이트웨이 형식에 맞춘다. Claude 는 반드시 여기서 만든 클라이언트로 부른다.

Codyssey 게이트웨이 규칙 (2026-09-24 실측)
  주소       https://copa.codyssey.kr  — Anthropic Messages API(/v1/messages) 형식
  인증       x-api-key (sk-cody… 키). OpenAI 형식(/v1/chat/completions)은 이 키로 403
  모델 이름  날짜 없이: claude-sonnet-4 · claude-haiku-4 · claude-opus-4-8
             날짜를 붙이면(claude-sonnet-4-20250514) 모델 오류가 아니라
             "API key is invalid" 401 로 거절한다 — 키를 의심하게 만드는 함정

그래서 여기서 지키는 것
  - 주소 기본값을 게이트웨이로 둔다
  - 모델 이름 끝의 날짜(-YYYYMMDD)는 떼고 보낸다
  - SDK 자동 재시도를 끈다 (max_retries=0). 켜 두면 타임아웃마다 2번 더 기다린다.
    재시도가 필요하면 각 기능이 정한 횟수만큼 직접 한다 (AI기능명세 6: 1회)
  - 키가 없으면 None 을 돌려준다. 호출하는 쪽은 규칙·템플릿으로 대체한다 — AI 가 없어도 기능은 동작한다
"""

from __future__ import annotations

import os
import re

import config  # noqa: F401 - .env 를 먼저 읽는다

GATEWAY_URL = "https://copa.codyssey.kr"

# 역할별 모델. 바꿀 때는 .env 에서 바꾼다.
MODEL_MAIN = "claude-sonnet-4"   # 학습 분해 에이전트처럼 여러 단계를 생각해야 하는 일
MODEL_FAST = "claude-haiku-4"    # 추천 이유 한두 문장처럼 짧고 빨라야 하는 일

_ENV_FOR = {"main": ("ANTHROPIC_MODEL", MODEL_MAIN), "fast": ("ANTHROPIC_HAIKU_MODEL", MODEL_FAST)}
_DATE_SUFFIX = re.compile(r"-\d{8}$")


def model(kind: str = "main") -> str:
    """역할(main / fast)에 맞는 게이트웨이 모델 이름."""
    env_name, default = _ENV_FOR[kind]
    name = (os.getenv(env_name) or default).strip()
    return _DATE_SUFFIX.sub("", name)


def get_client(timeout: float = 60):
    """게이트웨이용 Anthropic 클라이언트. 키가 없거나 SDK 가 없으면 None."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=os.getenv("ANTHROPIC_BASE_URL") or GATEWAY_URL,
        timeout=timeout,
        max_retries=0,
    )


def text_of(response) -> str:
    """응답에서 텍스트 블록만 이어 붙인다."""
    return "".join(
        getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text"
    ).strip()
