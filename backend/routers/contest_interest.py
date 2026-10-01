"""관심 공모전 (FR-CONT-07) — 실제 일은 services/contest_interest.py 가 한다.

  GET    /contest-interests                     내 관심 공모전
  POST   /contest-interests/preview  {contest_id}   준비 블록이 놓일 자리 미리 보기 (저장 안 함)
  POST   /contest-interests          {contest_id}   확인 후 등록 — 준비 블록 저장 (자리가 없으면 409)
  DELETE /contest-interests/{contest_id}        관심 해제 — 아직 안 한 준비 블록도 지운다
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from services import contest_interest, replan
from utils.auth import get_current_user

router = APIRouter(prefix="/contest-interests", tags=["contest-interests"])


class InterestRequest(BaseModel):
    contest_id: str = Field(min_length=1, max_length=64)


def _public(view: dict) -> dict:
    return {k: v for k, v in view.items() if not k.startswith("_")}


@router.get("")
def my_interests(user=Depends(get_current_user), db=Depends(get_db)) -> dict:
    return {"interests": contest_interest.list_interests(db, str(user.id))}


@router.post("/preview")
def preview(req: InterestRequest, user=Depends(get_current_user), db=Depends(get_db)) -> dict:
    try:
        return _public(contest_interest.preview(db, str(user.id), req.contest_id, replan.now_kst()))
    except contest_interest.InterestNotFound:
        raise HTTPException(status_code=404, detail="공모전을 찾을 수 없어요.") from None
    except replan.ReplanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("", status_code=201)
def register(req: InterestRequest, user=Depends(get_current_user), db=Depends(get_db)) -> dict:
    try:
        return _public(contest_interest.register(db, str(user.id), req.contest_id, replan.now_kst()))
    except contest_interest.InterestNotFound:
        raise HTTPException(status_code=404, detail="공모전을 찾을 수 없어요.") from None
    except replan.ReplanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.delete("/{contest_id}")
def unregister(contest_id: str, user=Depends(get_current_user), db=Depends(get_db)) -> dict:
    try:
        return contest_interest.unregister(db, str(user.id), contest_id)
    except contest_interest.InterestNotFound:
        raise HTTPException(status_code=404, detail="관심 등록한 공모전이 아니에요.") from None
