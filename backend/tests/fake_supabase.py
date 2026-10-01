"""테스트용 가짜 Supabase — 메모리에 행을 들고 supabase-py 의 체이닝 문법을 흉내 낸다.

실제 DB 를 건드리지 않고 저장·조회 로직을 확인할 때 쓴다. 누구나 가져다 써도 된다.

    from tests.fake_supabase import FakeSupabase
    db = FakeSupabase()
    app.dependency_overrides[get_db] = lambda: db
    ...
    db.rows("study_plans")   # 저장된 행 확인

지원: table().select(count='exact')/insert/upsert/update/delete · eq · in_ · lt · gte · order · limit · range · execute
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
    "plan_reschedule_runs": {"moved": 0, "unplaced": 0, "undone_at": None},
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
        self._offset = 0
        self._count = False

    # 동작
    def select(self, *_columns, count=None):
        self.op = "select"
        self._count = count == "exact"  # 결과에 전체 개수(count)를 함께 돌려준다
        return self

    def insert(self, values):
        self.op, self.payload = "insert", values
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def upsert(self, values, on_conflict=""):
        """on_conflict 열이 같은 행이 있으면 덮어쓰고, 없으면 넣는다."""
        self.op, self.payload = "upsert", values
        self._conflict = [c.strip() for c in on_conflict.split(",") if c.strip()] or ["id"]
        return self

    def delete(self):
        self.op = "delete"
        return self

    # 조건
    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def in_(self, column, values):
        self.filters.append((column, _In(values)))
        return self

    def lt(self, column, value):
        self.filters.append((column, _Lt(value)))
        return self

    def gte(self, column, value):
        self.filters.append((column, _Gte(value)))
        return self

    def lte(self, column, value):
        self.filters.append((column, _Lte(value)))
        return self

    def order(self, column, desc=False):
        self._order = (column, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        """supabase-py 처럼 양 끝을 포함한다 (0, 19 → 20개)."""
        self._offset, self._limit = start, end - start + 1
        return self

    def _matches(self, row):
        return all(
            v.has(row.get(c)) if isinstance(v, (_In, _Lt, _Gte, _Lte)) else row.get(c) == v
            for c, v in self.filters
        )

    def execute(self):
        table = self.db.tables.setdefault(self.name, [])
        if self.op == "insert":
            values = self.payload if isinstance(self.payload, list) else [self.payload]
            new = [self.db._new_row(self.name, v) for v in values]
            table.extend(new)
            return SimpleNamespace(data=[dict(r) for r in new])
        if self.op == "upsert":
            values = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for v in values:
                same = next((r for r in table if all(r.get(c) == v.get(c) for c in self._conflict)), None)
                if same is not None:
                    same.update(v)
                    out.append(same)
                else:
                    row = self.db._new_row(self.name, v)
                    table.append(row)
                    out.append(row)
            return SimpleNamespace(data=[dict(r) for r in out])
        hits = [r for r in table if self._matches(r)]
        if self.op == "update":
            for r in hits:
                r.update(self.payload)
            return SimpleNamespace(data=[dict(r) for r in hits])
        if self.op == "delete":
            self.db.tables[self.name] = [r for r in table if not self._matches(r)]
            # 외래키 cascade 흉내 — 계획을 지우면 딸린 단위·블록도 지운다
            gone = {r["id"] for r in hits}
            if self.name == "study_plans":
                for child in ("study_units", "plan_blocks", "plan_reschedule_runs", "plan_changes"):
                    self.db.tables[child] = [
                        r for r in self.db.tables.get(child, []) if r.get("plan_id") not in gone
                    ]
            # 블록을 지우면 기록·변경 내역은 남기고 연결만 끊는다 (on delete set null)
            if self.name == "plan_blocks":
                for child in ("study_sessions", "plan_changes"):
                    for r in self.db.tables.get(child, []):
                        if r.get("block_id") in gone:
                            r["block_id"] = None
            return SimpleNamespace(data=[dict(r) for r in hits])
        if self._order:
            column, desc = self._order
            # 빈 값은 맨 뒤로, 나머지는 값 그대로 비교 (숫자·문자 섞지 않는다)
            hits = sorted(hits, key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)
        total = len(hits)
        hits = hits[self._offset:]
        if self._limit is not None:
            hits = hits[: self._limit]
        return SimpleNamespace(data=[dict(r) for r in hits], count=total if self._count else None)


class _In:
    def __init__(self, values):
        self.values = list(values)

    def has(self, value):
        return value in self.values


class _Lt:
    def __init__(self, value):
        self.value = value

    def has(self, value):
        return value is not None and value < self.value


class _Gte:
    def __init__(self, value):
        self.value = value

    def has(self, value):
        # ISO-8601 문자열은 사전식 비교가 시간순 비교와 같아서 날짜 필터(created_at
        # 등)에 그대로 쓸 수 있다.
        return value is not None and value >= self.value


class _Lte:
    def __init__(self, value):
        self.value = value

    def has(self, value):
        return value is not None and value <= self.value
