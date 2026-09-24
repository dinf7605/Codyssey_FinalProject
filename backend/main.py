import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routers import admin, auth, batch, contests, goal, notifications, plan, settings, study
from routers import contest_demo

# ── .env 파일 읽기 ──
load_dotenv()

# ── FastAPI 앱 생성 ──
app = FastAPI(title="StudyPace API")
app.include_router(auth.router)
app.include_router(notifications.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(batch.router)
app.include_router(contest_demo.router)
app.include_router(contests.router)  # FR-CONT-03/10 (담당 D)
app.include_router(plan.router)    # FR-PLAN-* (담당 C)
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
