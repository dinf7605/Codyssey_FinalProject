"""비밀번호 추가 규칙 (FR-JOIN-01 · NFR-SEC-03) — 길이·조합 규칙(schemas/user.py) 다음에 본다.

  - 이메일 아이디(@ 앞)나 닉네임이 들어간 비밀번호는 거부한다 (3자 이상일 때, 대소문자 무시)
  - 자주 쓰이는 비밀번호 상위 1만 개(data/common_passwords.txt)는 거부한다.
    'Password1!' 처럼 흔한 비밀번호에 숫자·기호만 붙이거나 글자를 기호로 바꾼 것도 같은 것으로 본다

거부 사유는 한 문장으로 돌려준다. 통과하면 None.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

COMMON_FILE = Path(__file__).resolve().parents[1] / "data" / "common_passwords.txt"
MIN_PART = 3  # 이보다 짧은 이메일 아이디·닉네임은 우연히 겹치기 쉬워 보지 않는다

_LEET = str.maketrans({"@": "a", "4": "a", "0": "o", "1": "i", "!": "i", "3": "e", "$": "s", "5": "s", "7": "t"})

CONTAINS_PERSONAL = "비밀번호에 이메일 아이디나 닉네임을 넣을 수 없습니다."
TOO_COMMON = "너무 흔하게 쓰이는 비밀번호입니다. 다른 비밀번호를 정해 주세요."


@lru_cache(maxsize=1)
def common_passwords() -> frozenset[str]:
    lines = COMMON_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().lower() for line in lines if line.strip() and not line.startswith("#"))


def _forms(password: str) -> set[str]:
    """흔한 비밀번호와 견줄 모양들 — 소문자, 기호 뺀 것, 기호를 글자로 되돌린 것, 끝의 숫자·기호 뺀 것."""
    lower = password.lower()
    forms = {lower, re.sub(r"[^a-z0-9]", "", lower), re.sub(r"[^a-z0-9]", "", lower.translate(_LEET))}
    forms |= {re.sub(r"[^a-z]+$", "", f) for f in list(forms)}
    return {f for f in forms if len(f) >= 4}  # 너무 짧게 깎인 모양은 우연히 겹치기 쉽다


def problem(password: str, *, email: str = "", nickname: str = "") -> str | None:
    lower = password.lower()
    local = email.split("@", 1)[0].lower()
    for part in (local, (nickname or "").strip().lower()):
        if len(part) >= MIN_PART and part in lower:
            return CONTAINS_PERSONAL
    common = common_passwords()
    if any(f in common for f in _forms(password)):
        return TOO_COMMON
    return None
