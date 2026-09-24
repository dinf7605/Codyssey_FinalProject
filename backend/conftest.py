"""pytest 가 backend/ 를 임포트 경로로 잡게 한다.

이게 없으면 테스트에서 `from schemas.plan import ...` 가 안 된다.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch):
    """테스트는 실제 Claude 를 부르지 않는다 — 느리고 비용이 든다.

    .env 에 키가 있어도 테스트 중에는 지운다. AI 가 없을 때의 대체 동작(템플릿)을 검증하는 셈이다.
    실제 호출 확인은 backend/README.md 의 실측 절차로 따로 한다.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
