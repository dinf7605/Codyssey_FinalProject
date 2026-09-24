"""테스트용 가짜 Supabase — 메모리에 행을 들고 supabase-py 의 체이닝 문법을 흉내 낸다.

실제 DB 를 건드리지 않고 저장·조회 로직을 확인할 때 쓴다. 누구나 가져다 써도 된다.

    from tests.fake_supabase import FakeSupabase
    db = FakeSupabase()
    app.dependency_overrides[get_db] = lambda: db
    ...
    db.rows("study_plans")   # 저장된 행 확인

지원: table().select/insert/update/delete · eq · order · limit · execute
기본값: id 자동 생성(uuid), study_plans.status='active', created_at 은 넣은 순서대로 증가
"""

from __future__ import annotations

import itertools
import uuid
from types import SimpleNamespace

_DEFAULTS = {
    "study_plans": {"status": "active"},
    "plan_blocks": {"locked": False, "done": False},
    "study_units": {"estimated": False, "prerequisites": []},
}


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self._clock = itertools.count(1)

    def table(self, name: str) -> "_Query":
        return _Query(self, name)

    def rows(self, name: str) -> list[dict]:
        return self.tables.get(name, [])

    def _new_row(self, name: str, values: dict) -> dict:
        row = {**_DEFAULTS.get(name, {}), **values}
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", f"2026-01-01T00:00:{next(self._clock):02d}+00:00")
        return row


class _Query:
    def __init__(self, db: FakeSupabase, name: str):
        self.db, self.name = db, name
        self.op, self.payload = "select", None
        self.filters: list[tuple[str, object]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    # 동작
    def select(self, *_columns):
        self.op = "select"
        return self

    def insert(self, values):
        self.op, self.payload = "insert", values
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def delete(self):
        self.op = "delete"
        return self

    # 조건
    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def order(self, column, desc=False):
        self._order = (column, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, row):
        return all(row.get(c) == v for c, v in self.filters)

    def execute(self):
        table = self.db.tables.setdefault(self.name, [])
        if self.op == "insert":
            values = self.payload if isinstance(self.payload, list) else [self.payload]
            new = [self.db._new_row(self.name, v) for v in values]
            table.extend(new)
            return SimpleNamespace(data=[dict(r) for r in new])
        hits = [r for r in table if self._matches(r)]
        if self.op == "update":
            for r in hits:
                r.update(self.payload)
            return SimpleNamespace(data=[dict(r) for r in hits])
        if self.op == "delete":
            self.db.tables[self.name] = [r for r in table if not self._matches(r)]
            # 외래키 cascade 흉내 — 계획을 지우면 딸린 단위·블록도 지운다
            if self.name == "study_plans":
                gone = {r["id"] for r in hits}
                for child in ("study_units", "plan_blocks"):
                    self.db.tables[child] = [
                        r for r in self.db.tables.get(child, []) if r.get("plan_id") not in gone
                    ]
            return SimpleNamespace(data=[dict(r) for r in hits])
        if self._order:
            column, desc = self._order
            # 빈 값은 맨 뒤로, 나머지는 값 그대로 비교 (숫자·문자 섞지 않는다)
            hits = sorted(hits, key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)
        if self._limit is not None:
            hits = hits[: self._limit]
        return SimpleNamespace(data=[dict(r) for r in hits])
