import os

import config  # noqa: F401 - .env 를 가장 먼저 읽는다 (config.py 설명 참고)
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db import DatabaseNotConfigured
from routers import admin, auth, auth_google, batch, contest_interest, contests, goal, google_calendar, memories, notifications, plan, settings, study

# ── FastAPI 앱 생성 ──
app = FastAPI(title="StudyPace API")


# ── DB 키가 비어 있으면 서버는 뜨고, DB 를 쓰는 요청만 503 ──
@app.exception_handler(DatabaseNotConfigured)
def database_not_configured(_: Request, exc: DatabaseNotConfigured):
    return JSONResponse(status_code=503, content={"detail": str(exc)})

app.include_router(auth.router)
app.include_router(auth_google.router)  # FR-AUTH-02 구글 로그인
app.include_router(notifications.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(batch.router)
app.include_router(contests.router)  # FR-CONT-03/10 (담당 D)
app.include_router(contest_interest.router)  # FR-CONT-07 관심 공모전 준비 블록
app.include_router(memories.router)  # FR-MEM-01/02 (담당 D)
app.include_router(plan.router)    # FR-PLAN-* (담당 C)
app.include_router(google_calendar.router)  # FR-PLAN-01 캘린더 바쁜 시간 (담당 C)
app.include_router(study.router)   # FR-STUDY-* (담당 C)
app.include_router(goal.router)    # FR-GOAL-* (담당 B)

# ── CORS 설정 (프론트-백엔드 도메인 통신 허가) ──
# .env의 FRONTEND_ORIGIN 값을 읽고, 없으면 로컬 기본값 사용
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],   # 허용할 프론트 주소
    allow_credentials=True,            # 쿠키·인증정보 허용
    allow_methods=["*"],               # GET, POST 등 모든 메서드 허용
    allow_headers=["*"],               # 모든 헤더 허용
)


# ── /health 엔드포인트 (서버 생존 신호등) ──
@app.get("/health")
def health_check():
    return {"status": "ok"}
