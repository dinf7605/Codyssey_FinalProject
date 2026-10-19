# Must 기능 확인표 — 적어 둔 대로 동작하는가

> 필수요건 "Must 기능이 적어 둔 대로 동작" 의 근거. **10-19 개정: Must 는 [기능요구명세서](기능요구명세서.md)의 10개**다
> (운영진 요청으로 Must 38개를 10개로 줄였다 — 원래 ID 18개를 10개로 묶고, 나머지 20개는 Should 로 내렸다).
> 아래 표는 개정 전 Must 38개를 하나씩 어디서 확인하고(화면 · API), 어디에 구현돼 있고(코드), 무엇으로 검증했는지(테스트 · 점검) 적은 것이다.
> 지금 Must 인 18개 ID 는 **M1~M10** 으로, Should 로 내린 20개는 상태 칸에 **Should** 로 표시했다. Should 로 내렸어도 기능은 그대로 동작한다.
> 기준: 2026-10-12 `main` · 배포 https://codyssey-final-project.vercel.app (화면 12개 · 공개 API 응답 확인 10-12 · 10-19 `/health/ready` 정상).
> 로그인이 필요한 기능은 README [평가자 접속 방법](../README.md#평가자-접속-방법)대로 확인한다.

| 표시 | 뜻 |
|---|---|
| ✅ | 명세대로 동작 — 화면 · API 에서 확인했고 자동 테스트 또는 점검 기록이 있다 |
| ✅* | 동작하지만 명세의 **방법**을 바꿨다 — 바꾼 이유는 비고와 기획서에 적었다 |

## 메인 · 대시보드 · 진도

| ID | 기능 | 확인 (화면 · API) | 구현 | 검증 | 상태 |
|---|---|---|---|---|---|
| FR-MAIN-02 | 로그인 상태에 따라 다른 메뉴 | 모든 화면 상단 · 하단 메뉴 (비회원: 로그인 / 회원: 내 계정 · 관리자는 '관리자') · 첫 화면 헤더 | `components/TopBar.js` · `SideNav.js` · `CurrentAccount.js` · `HomeAuthActions.js` | 점검 7 · 9차, 10-06 첫 화면 수정 | ✅ · Should |
| FR-MAIN-03 (M8) | 오늘의 학습 블록 | `/dashboard` 오늘의 블록 · `GET /plan/active` | `app/(app)/dashboard/page.js` · `components/DayTimeline.js` | 점검 7 · 8차 | ✅ |
| FR-PACE-01 | 중간 목표 ('언제까지 어디까지') 자동 | `/dashboard` 이번 주 체크포인트 | `lib/pace.js` · `services/alarms.py` (주마다 마지막 블록 = 체크포인트) | `tests/test_alarms.py` | ✅ · Should |
| FR-PACE-02 | 진도 기준선 (지금 어디까지 했어야 하나) | `/dashboard` 진도 신호등의 '며칠 앞섬 / 뒤처짐' | `lib/pace.js` — 기준선 = 확정한 계획(재조정 뒤엔 새 계획) | 점검 기록 (대시보드) | ✅* 직선 기준선 대신 확정 계획을 기준선으로 (앞쪽에 몰린 계획이 늘 '앞섬'으로 보이는 문제) · Should |
| FR-PACE-04 | 진도 신호등 | `/dashboard` (계획 시작 3일 뒤부터 · 3일 주의 · 7일 경고) | `lib/pace.js` · `dashboard/page.js` | 점검 기록 | ✅ · Should |
| FR-UI-01 | 학습량에 따른 적응형 테마 | 레벨 1~5 에 따라 대시보드 구성이 열림 | `lib/growth.js` · `dashboard/page.js` | `tests/test_aggregator.py` (레벨) | ✅ · Should |
| FR-MAIN-06 | 개인정보 처리방침 | `/privacy` (모든 화면 아래 링크) | `app/privacy/page.js` | 배포 200 확인 | ✅ · Should |

## 인증 · 가입

| ID | 기능 | 확인 | 구현 | 검증 | 상태 |
|---|---|---|---|---|---|
| FR-AUTH-01 (M1) | 이메일 로그인 | `/login` · `POST /auth/login` (5회 실패 60초 잠금 · 실패 문구 통일 · 인증 전이면 안내) | `routers/auth.py` · `services/login_guard.py` | `tests/test_login_lock_contest_fix.py` · `test_auth_signup.py` | ✅ |
| FR-JOIN-01 (M1) | 이메일 · 비밀번호 · 닉네임 가입 | `/signup` · `POST /auth/signup` (조건 실시간 표시 · 흔한 비밀번호 거부 · 가입 후 인증 메일 안내) | `routers/auth.py` · `services/password_policy.py` · `app/signup/page.js` | `tests/test_auth_signup.py` · `test_auth_password_feedback.py` | ✅ |
| FR-JOIN-02 (M1) | 개인정보 수집 동의 | `/signup` 필수 동의 (내용 보기 창) · 구글 첫 로그인도 같은 동의 | `components/SignupConsentFields.js` · `routers/auth_google.py` | `tests/test_auth_google.py` | ✅ |
| FR-JOIN-03 (M1) | AI 이용 고지 | `/signup` 필수 동의 · 문구 버전이 바뀌면 재동의 (`GET /auth/consent`) | `SignupConsentFields.js` · `ReconsentGate` · `AI_NOTICE_VERSION` | `tests/test_auth_signup.py` | ✅ |

## 목표 탐색 (온보딩)

| ID | 기능 | 확인 | 구현 | 검증 | 상태 |
|---|---|---|---|---|---|
| FR-GOAL-01 (M2) | 관심분야 입력 · 건너뛰기 | `/onboarding` 1단계 (칩 · 직접 입력 · 건너뛰기) | `app/onboarding/page.js` · `GET /goal/tags` | 점검 7차 | ✅ |
| FR-GOAL-11 | 관심분야 없이도 비슷한 분야 추천 | 1단계 건너뛰기 → `GET /goal/popular` · `POST /goal/suggest` | `routers/goal.py` · `services/goal_recommender.py` | `tests/test_goal_router.py` | ✅ · Should |
| FR-GOAL-02 (M2) | 주간 가용 시간 입력 | `/onboarding` 2단계 (요일 × 시간대 · 하루 최대 공부 시간) | `onboarding/page.js` · `lib/planInput.js` | 점검 7 · 사전 점검 | ✅ |
| FR-GOAL-03 (M3) | 관심분야에 맞는 목표 후보 | 3단계 · `POST /goal/recommend` (Claude 관련성 0.60 이상) | `services/goal_claude.py` · `goal_catalog.py` | `tests/test_goal_claude.py` · 정답셋 100% | ✅* 임베딩 대신 Claude 관련성 판단 (09-29, 게이트웨이에 임베딩 API 없음) |
| FR-GOAL-04 (M3) | 기간 적합성 판정 | 3단계 — 기한 안에 못 끝내는 목표는 빼고 빠듯하면 표시 | `services/goal_feasibility.py` | `tests/test_goal_feasibility.py` | ✅ |
| FR-GOAL-09 (M3) | 최소 필요 기간 | 추천 카드 '준비 약 N주' · `POST /goal/feasibility` | `goal_feasibility.py` | `tests/test_goal_feasibility.py` | ✅ |
| FR-GOAL-05 (M3) | 추천 카드 3~5개 + 이유 | 3단계 카드 · 'AI 추천' 배지 · 이유가 계산과 반대면 템플릿 | `goal_recommender.py` · `goal_claude.py` | `tests/test_goal_router.py` · 정답셋 사실성 100% | ✅ |
| FR-GOAL-07 (M4) | 목표 확정 → 일정 생성 | 4단계 확정 · `POST /goal/confirm` → `/schedule` (목표 최대 2개) | `routers/goal.py` · `components/PlanBuilder.js` | `tests/test_multiplan.py` | ✅ |
| FR-GOAL-12 | 비회원 이용 제한 | 비회원 AI 추천 24시간 3회 + IP 해시 15회 · 비용 한도 80% 차단 | `services/goal_limiter.py` · `ai_budget.py` | `tests/test_goal_limiter.py` · `test_spec_details.py` | ✅ · Should |

## 일정 · 학습

| ID | 기능 | 확인 | 구현 | 검증 | 상태 |
|---|---|---|---|---|---|
| FR-PLAN-01 | 구글 캘린더로 빈 시간 찾기 | `/schedule` 계획 만들기 '캘린더에서 가져오기' · `GET /calendar/connect` · `POST /calendar/busy` | `routers/google_calendar.py` | `tests/test_google_calendar.py` · 점검 10차 | ✅* 바쁜 시간만 1회 읽고 토큰을 저장하지 않음 (개인정보 최소화) · Should |
| FR-PLAN-02 (M5) | 학습 분해 (AI Agent) | 계획 만들기 · `POST /plan/decompose/stream` (실제 진행 단계 표시) | `services/decomposer.py` · `agent_tools.py` | `tests/test_decomposer.py` · `test_agent_tools.py` · 실측 28~35초 | ✅ |
| FR-PLAN-03 (M6) | 빈 시간에 자동 배치 | 계획 미리보기 · `POST /plan/schedule` · `POST /plan/validate` (규칙 위반 0건) | `services/scheduler.py` · `validator.py` | `tests/test_scheduler.py` · `test_validator.py` | ✅ |
| FR-PLAN-04 (M7) | 주 · 월 일정 조회 | `/schedule` 주 · 월 달력 · 미배치 단원 표시 | `components/PlanCalendar.js` · `GET /plan/active` | `tests/test_unplaced_notes.py` · 점검 7 · 8차 | ✅ |
| FR-PLAN-06 | 야간 재조정 | 매일 03:00 `POST /plan/nightly` (GitHub Actions) · 변경 내역 · 되돌리기 | `services/replan.py` · `.github/workflows/plan-jobs.yml` | `tests/test_replan.py` · 7일 7회 모두 성공 ([운영 보고서](ops-report.md)) | ✅ · Should |
| FR-STUDY-01 (M9) | 학습 타이머 | `/study` (5분 미만 미기록 · 30분 무조작 멈춤 · 오프라인 보관) · 블록 공부 방법 | `components/StudyTimer.js` · `POST /study/sessions` | `tests/test_plan_store.py` · 점검 9차 | ✅ |
| FR-STUDY-02 (M9) | 블록 완료 · 24시간 안 취소 | `/study` 완료 · 예상의 절반 미만이면 끝냈는지 묻기 · `DELETE /study/blocks/{id}/done` | `routers/study.py` · `services/replan.py` | `tests/test_replan.py` · `test_plan_store.py` | ✅ |
| FR-STUDY-03 (M10) | 학습 즉시 집계 | 완료 직후 `GET /study/stats` (누적 · 연속 · 주간 달성률) | `services/aggregator.py` | `tests/test_aggregator.py` | ✅* Redis 대신 PostgreSQL 집계 (5~10명 규모, 기획서 5-2) |

## 알림 · 공모전 · 메모리 · 마이페이지

| ID | 기능 | 확인 | 구현 | 검증 | 상태 |
|---|---|---|---|---|---|
| FR-ALARM-01 | 학습 시작 알림 | `/notifications` · 블록 10분 전 (알림 워커 1분 주기) | `workers/notification_worker.py` · `services/alarms.py` | `tests/test_alarms.py` · `test_notification_scheduler.py` · 10-05 실제 도착 확인 | ✅ · Should |
| FR-CONT-01 | 공고 수집 배치 | 매일 05:00 `POST /contests/collect` (GitHub Actions · robots.txt · 3초 간격) | `services/wevity_collector.py` · `contest-jobs.yml` | `tests/test_wevity_collector.py` · 7일 8회 모두 성공 | ✅ · Should |
| FR-CONT-02 | 수집 공고 관련성 검색 | `/contests` AI 추천 · 조건 검색 | `services/contest_claude.py` · `contest_repository.py` | `tests/test_contest_claude.py` | ✅* 임베딩 색인 대신 Claude 관련성 판단 (09-29) — 명세의 '임베딩 색인' 단계는 없앰 · Should |
| FR-CONT-10 | 준비 기간 산정 | `/contests/[id]` '마감까지 N일' 판정 (내 계획의 주간 시간 사용) | `services/contest_service.py` · `preparation_time_standards` | `tests/test_contests.py` | ✅ · Should |
| FR-CONT-04 | 공모전 주간 추천 | 월 09:00 `POST /contests/recommend-weekly` · `GET /contests/recommendations` | `services/contest_recommender.py` | `tests/test_contest_personalization.py` | ✅ · Should |
| FR-CONT-05 | 추천 이유 표시 | `/contests` 카드의 이유 + 'AI 추천' 배지 | `components/ContestCard.js` · `contest_claude.py` | 정답셋 사실성 100% | ✅ · Should |
| FR-CONT-08 | 추천 평가 | `/contests` 카드 '도움됨 / 안 맞음' · `POST /contests/{id}/feedback` → 다음 추천에서 제외 | `components/ContestFeedback.js` · `routers/contests.py` | `tests/test_contest_personalization.py` | ✅ · Should |
| FR-MEM-02 | 저장된 학습 정보 삭제 | `/mypage` 저장된 학습 정보 — 항목별 · 전체 · `DELETE /memories/{id}` · `DELETE /memories` | `components/AccountMemories.js` · `routers/memories.py` | `tests/test_study_memory.py` | ✅ · Should |
| FR-MY-05 | 알림 강도 · 방해금지 | `/mypage` 알림 설정 (보통 · 강 · 23~07시) · `PUT /settings/notifications` | `components/NotificationSettings.js` · `services/alarms.py` | `tests/test_settings.py` · `test_alarms.py` | ✅ · Should |
| FR-MY-04 | 회원 탈퇴 | `/mypage` 회원 탈퇴 · `DELETE /settings/withdraw` (서비스 데이터 즉시 삭제 · 프로필 1년 분리 보관) | `components/AccountSettings.js` · `routers/settings.py` | `tests/test_settings.py` · 10-06 실제 탈퇴 → 보관본 확인 | ✅ · Should |

## 요약

- **지금 Must 10개(M1~M10, 원래 ID 18개) 모두 동작** — 방법을 바꾼 것은 목표 후보 매칭(M3) · 학습 집계(M10) 2개(✅*)
- 개정 전 Must 38개도 모두 동작 — 33개는 명세대로(✅), 5개는 방법을 바꿔 동작(✅*): 진도 기준선 · 목표 후보 매칭 · 캘린더 · 학습 집계 · 공고 검색
  (바꾼 이유는 [기획서](기획서_학습플래너.md) 4-4 · 5-2 와 README [계획에서 바뀐 점](../README.md#계획에서-바뀐-점))
- 자동 테스트 546개 (`cd backend && python -m pytest`) · 프론트 lint · build 는 CI 에서 push 마다 실행
- 날짜별 점검 내용은 README [중간 점검](../README.md#중간-점검) 1~12차
