# StudyPace 백엔드

Python + FastAPI. AI 호출과 일정 계산이 여기서 돈다.

## 실행

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload     # http://localhost:8000/docs
pytest -q                     # 테스트
```

`/docs` 에서 화면 없이 API를 눌러 볼 수 있다. 프론트와 따로 검증할 때 쓴다.

### 환경변수

루트의 `.env.example` 을 복사해 `.env` 로 만들고 값을 채운다. `.env` 는 `config.py` 한 곳에서만 읽는다.
**`.env` 가 셸 환경변수보다 우선한다** — Claude Code 같은 도구가 셸에 `ANTHROPIC_BASE_URL` 을 미리 넣어 두는 경우가 있어서다.

키가 비어 있어도 서버는 뜬다.
- `ANTHROPIC_API_KEY` 가 없으면 AI 대신 규칙·템플릿으로 동작한다 (학습 분해 → 표준 커리큘럼, 추천 이유 → 규칙 문구)
- Supabase 키가 없으면 DB 를 쓰는 요청만 **503** 과 함께 빠진 변수 이름을 돌려준다

### Claude 호출 기준 — Codyssey 게이트웨이

**Claude 는 `services/llm.py` 의 `get_client()` · `model()` 로만 부른다.** `anthropic.Anthropic(...)` 을 직접 만들지 않는다.

| 항목 | 기준 | 어기면 |
|---|---|---|
| 주소 | `https://copa.codyssey.kr` (Anthropic `/v1/messages` 형식) | `api.anthropic.com` 으로 가서 401 |
| 모델 이름 | 날짜 **없이** — `llm.model("main")` = `claude-sonnet-4`, `llm.model("fast")` = `claude-haiku-4` | `claude-sonnet-4-20250514` 처럼 날짜를 붙이면 모델 오류가 아니라 **"API key is invalid"** 401 — 키를 의심하게 만드는 함정. `llm.model()` 이 날짜를 떼어 준다 |
| 자동 재시도 | 끔 (`max_retries=0`) | SDK 가 타임아웃마다 2번 더 기다려 사용자 대기가 3배 |
| 시간 제한 | 기능마다 `get_client(timeout=…)` 로 준다 — 학습 분해 전체 60초, 짧은 문장 20초 | |
| 키 없음·실패 | `get_client()` 가 `None` → 규칙·템플릿으로 대체. 결과에 AI 여부를 남긴다 (`source`, `ai_generated`) | AI 가 조용히 실패해도 모른다 — B 의 추천 이유가 실제로 그랬다 |
| OpenAI 형식 | 이 키로는 `/v1/chat/completions` 가 **403**. 임베딩 API 도 없다 | 임베딩은 별도 수단이 필요 (D·B 과제) |

쓸 수 있는 모델: `claude-sonnet-4` · `claude-haiku-4` · `claude-opus-4-8`. 바꿀 때는 `.env` 의 `ANTHROPIC_MODEL` / `ANTHROPIC_HAIKU_MODEL`.
테스트는 `conftest.py` 가 키를 지워서 실제 Claude 를 부르지 않는다 (느리고 비용이 든다).

### DB (Supabase)

프로젝트 `studypace` (서울 `ap-northeast-2`, 무료 플랜) — `https://spgrerxkdavykunujipn.supabase.co`

스키마는 `migrations/` 의 SQL 이 전부다. 대시보드에서 손으로 테이블을 만들지 않는다 — 새 프로젝트에서 똑같이 재현할 수 없게 된다.

| 파일 | 담당 | 테이블 |
|---|---|---|
| `000_core_users_notifications.sql` | E | `users`, `notification_logs` |
| `001_contest_personalization.sql` | D | `contests`, `contest_embeddings`, `preparation_time_standards`, `contest_recommendations`, `contest_feedback`, `user_memories`, `batch_runs` |
| `002_plan_study.sql` | C | `study_plans`, `study_units`, `plan_blocks`, `study_sessions`, `ai_call_logs` |
| `003_advisor_fixes.sql` | — | Supabase 점검 도구 경고 정리 (정책 성능, 함수 search_path, vector 스키마, 외래키 인덱스) |
| `004_db_standard.sql` | — | 아래 DB 기준으로 통일 (`auth_id` → `user_id`, `password_hash` 삭제) |
| `008_replan_changes.sql` | C | `plan_reschedule_runs`, `plan_changes` + `study_plans.availability`, `plan_blocks.done_at` (재조정·변경 내역·완료 취소) |
| `009_curriculum.sql` | C | `curriculum_units` — 정보처리기사 필기·SQLD·ADsP 출제 범위 70항목 (학습 분해 에이전트의 근거) |
| `010_withdrawal_retention.sql` | E | 탈퇴 프로필 1년 보관 (`private.withdrawn_profiles`, `auth.users` 삭제 전 트리거, `pg_cron` 삭제 작업) |
| `011_admin_ai_call_logs.sql` | E | `ai_call_logs` 날짜별 조회 인덱스 (관리자 화면) |
| `012_unit_removed.sql` | C | `study_units.removed_at` — 직접 지운 단위를 미배치와 구분 |
| `013_preparation_standards_seed.sql` | D | `preparation_time_standards` 17개 분야 시드 (팀 추정치) |
| `007_goal_feedback.sql` | B | `goal_feedback` — 목표 추천 피드백 (FR-GOAL-08). 09-28 적용, 정책을 `(select auth.uid())` 로 고쳐서 |
| `014_notification_settings.sql` | E | `user_notification_settings`(알림 켜기·방해금지·강도) + `notification_logs.block_id`·중복 방지 인덱스. 개인 DB 기준이던 005·006 을 공용 기준으로 다시 쓴 것 (005·006 파일은 삭제) |
| `015_ai_request_logs.sql` | E | `ai_request_logs` — 학습 분해의 Claude 요청 한 번에 한 행 (성공·실패, 오류 종류, 토큰). 사용자 식별자·본문 없음. 09-29 적용 · 저장은 `AI_REQUEST_METRICS_ENABLED=1` 일 때만 |
| `016_wevity_link_only.sql` | D | 위비티 제목·링크 전용 공고의 빈 마감일 허용. 09-29 적용 — SQL Editor 로 적용해 Migrations 목록에는 없다 |
| `017_contest_title_vectors.sql` | D | 이전 OpenAI 임베딩 설계의 선택적 RPC. Claude 제목 추천에는 필요하지 않음 |

공용 DB 에 무엇이 적용됐는지는 Supabase 대시보드 → Database → Migrations 에서 본다 (적용한 이름이 이 표의 파일 이름과 같다).

키 받는 곳: Supabase 대시보드 → Project Settings → API Keys.
`SUPABASE_URL` · `SUPABASE_ANON_KEY` 는 공개돼도 되는 값, 비밀 키(`sb_secret_…`)는 **`SUPABASE_SERVICE_ROLE_KEY` 한 곳**에만 넣는다.

#### DB 기준 — 새 테이블·새 코드는 이대로

**연결 (`db.py`)** — 클라이언트는 두 가지, 용도를 섞지 않는다.

| 함수 | 키 | 쓰는 곳 | 규칙 |
|---|---|---|---|
| `get_supabase_client()` | 서비스 키 | 테이블 읽기·쓰기, 토큰 확인(`auth.get_user`), 계정 삭제 | 한 번 만들어 재사용. **RLS 를 통과하므로 `.eq("user_id", user.id)` 를 코드에서 반드시 건다** |
| `new_auth_client()` | 공개 키 | 가입(`sign_up`)·로그인(`sign_in_with_password`)만 | **요청마다 새로 만든다.** 로그인하면 클라이언트가 그 사용자 세션을 품어서, 공유하면 이후 다른 사람 요청이 마지막 로그인 사용자 권한으로 조회된다 |

**스키마**

| 항목 | 기준 |
|---|---|
| 변경 방법 | `migrations/NNN_설명.sql` 만. 대시보드에서 손으로 만들지 않는다. 이미 적용한 파일은 고치지 않고 다음 번호로 덮어쓴다 |
| 테이블·컬럼 이름 | `snake_case`, 테이블은 복수형 (`study_plans`) |
| 사용자 참조 | **`user_id uuid not null references auth.users(id) on delete cascade`** — 탈퇴하면 딸린 데이터가 자동으로 지워진다 (FR-MY-04) |
| 기본키 | 외부에 노출되는 행은 `uuid default gen_random_uuid()`, 로그·기록은 `bigint generated always as identity` |
| 시간 | `timestamptz` (날짜만이면 `date`), 생성 시각은 `created_at default now()` |
| 값 제한 | 상태값·범위는 `check` 로 DB 에서 막는다 (`source in ('agent','partial','template')`) |
| RLS | **모든 테이블에 켠다.** 브라우저에 보여줄 것은 `select` 정책 `(select auth.uid()) = user_id`. 쓰기는 백엔드만 — 쓰기 정책은 만들지 않는다. 백엔드 전용 테이블은 정책 없이 둔다 |
| 비밀번호·토큰 | DB 에 저장하지 않는다. 비밀번호는 Supabase Auth 가 가진다 |
| 적용 후 | Supabase 점검 도구(Advisors)의 WARN 을 0 으로 만든다 |

#### 같이 작업할 때 DB 바꾸는 순서

**DB 는 팀 공용 하나(`spgrerxkdavykunujipn`)만 쓴다.** 개인 Supabase 프로젝트에서 만든 테이블은 팀 코드와 맞지 않는다 —
09-27 에 개인 DB 기준(`auth_id`)으로 짠 가입·탈퇴 코드가 공용 DB(`user_id`)에서 동작하지 않은 것이 이 때문이다 (루트 README 개발 기록 5차 점검 참고).

**처음 한 번**

1. 루트 `.env` 의 `SUPABASE_URL` · `SUPABASE_ANON_KEY` · `SUPABASE_SERVICE_ROLE_KEY` 를 공용 프로젝트 값으로 바꾼다.
   키는 대시보드 → Project Settings → API Keys. 비밀 키는 `.env` 에만 두고 커밋·메신저 공유하지 않는다
2. 대시보드를 봐야 하면 공용 프로젝트 소유자에게 Organization 멤버 초대를 받는다
3. 개인 DB 에 만들어 둔 테이블·데이터는 **옮기지 않는다.** 필요한 구조만 아래 순서대로 migration 파일로 다시 쓴다

**테이블·컬럼·시드를 바꿀 때마다**

| 순서 | 할 일 | 왜 |
|---|---|---|
| 1 | `git pull` → `migrations/` 의 마지막 번호 +1 을 쓴다. 팀 채널에 "014 씁니다" 로 먼저 알린다 | 둘이 같은 번호를 쓰면 순서가 꼬인다 |
| 2 | `migrations/NNN_설명.sql` 작성 — 맨 위에 담당·이유 주석, 위 **스키마 기준** 그대로 (`user_id` 참조, RLS, `check`). `create table if not exists` · `add column if not exists` 처럼 두 번 돌려도 되게 | 적용이 중간에 끊겨도 다시 돌릴 수 있다 |
| 3 | 그 테이블을 쓰는 코드·테스트와 **같은 커밋**으로 올린다. 코드의 테이블·컬럼 이름이 파일과 글자까지 같은지 확인 | 파일만 있고 코드가 없거나 그 반대면 배포에서 깨진다 |
| 4 | 공용 DB 적용은 **한 사람**이 한다 (지금은 C). 파일을 push 하고 "014 적용 부탁" 을 남긴다 | 적용 기록(Database → Migrations)이 한 목록에 남아야 무엇이 적용됐는지 헷갈리지 않는다. 각자 SQL Editor 에서 돌리면 기록이 빠진다 |
| 5 | 적용 후 Advisors WARN 0 확인 → 위 표에 한 줄 추가 → 팀에 "pull 받으세요" | 다른 사람 로컬 코드가 새 구조를 알게 |

**하지 않는다**

- 이미 적용한 파일을 고치기 — 공용 DB 에는 반영되지 않는다. 고칠 것은 다음 번호에 `alter table` 로
- 다른 담당의 테이블을 말없이 바꾸기 — 담당(위 표)에게 먼저 묻는다
- 대시보드에서 손으로 테이블을 만들거나 행을 넣고 지우기 — 시드도 migration(예: `013`)이나 스크립트(예: `scripts/collect_contests.py`)로

---

## 담당 C — 일정 · 학습 (`FR-PLAN-*` / `FR-STUDY-*`)

### 핵심 설계: LLM을 쓰는 곳과 쓰지 않는 곳

| 파일 | 하는 일 | LLM |
|---|---|:---:|
| `services/decomposer.py` | 목표를 학습 단위로 쪼갠다 | **사용** |
| `services/scheduler.py` | 학습 단위를 빈 시간에 놓는다 | 미사용 |
| `services/validator.py` | 규칙 위반을 검사한다 | 미사용 |
| `services/aggregator.py` | 누적·연속·레벨을 계산한다 | 미사용 |

**배치를 LLM에 맡기지 않는 이유** — 같은 입력에 항상 같은 결과가 나와야 검증할 수 있다.
"어제와 다른 일정표"는 신뢰할 수 없고, 마감 초과·선행 위반 0건을 보장할 수도 없다.
그래서 쪼개는 일만 AI가 하고, 놓는 일은 규칙으로 한다.

덕분에 **AI가 실패해도 일정은 항상 만들어진다.**

### 학습 분해 에이전트 (`FR-PLAN-02`)

`services/decomposer.py` — 이 프로젝트에서 AI Agent를 쓰는 유일한 곳이다.

```
목표 입력 → Claude 에게 질문 → 도구 호출 → 결과 반환 → 반복(최대 5회) → JSON 스키마 검증
                                                                    ↓ 실패
                                                            표준 커리큘럼 템플릿
```

| 항목 | 값 | 근거 |
|---|---|---|
| 도구 | 6종 (`services/agent_tools.py`) — 목업 없음, 아래 표 | AI기능명세 1 |
| 최대 반복 | **5회** | 3회로는 검색→추정→배치 연계가 끊기고, 8회 이상은 결과 차이 없이 비용만 증가 |
| 모델 | `claude-sonnet-4` | 아래 실측 — haiku 보다 8초 느리지만 단위를 더 잘게 나누고 추정 표시가 정확 |
| 시간 제한 | **전체 60초** (호출당 아님) | NFR-PERF-01. 각 호출에는 남은 시간만 준다 |
| SDK 자동 재시도 | **끔** (`max_retries=0`) | 켜 두면 타임아웃마다 2번 더 기다려 2분을 넘긴다 |
| 스키마 강제 | 도구에 `strict: true` | 인자가 스키마를 반드시 통과 → 검증 실패 폴백 자체가 줄어든다 |
| 실패 시 | 1회 재시도 → 템플릿 대체 | AI기능명세 6 |
| 사용자 확인 필요 | `save_plan` | 되돌리기 어려운 동작은 에이전트가 직접 실행하지 않는다 |
| 오늘 날짜 | 프롬프트에 넣는다 | 안 넣었더니 모델이 2024~2025년 날짜로 빈 시간을 조회했다 |
| 단위 수 | 최대 25개, 짧은 항목은 같은 과목끼리 합 120분 이하로 묶는다 | 항목마다 하나씩 쓰면 마지막 JSON 이 2,200토큰·27초가 되어 60초를 넘기기도 했다 |

**도구가 읽는 곳**

| 도구 | 읽는 곳 | 없을 때 |
|---|---|---|
| `search_curriculum` | `curriculum_units` 테이블 (마이그레이션 009). `goal_id` 가 `custom` 이면 목표 이름으로 찾는다 | 빈 목록 + "단위를 estimated=true 로" 안내 |
| `estimate_effort` | 이번 목표의 커리큘럼 권장 시간 × 수준 배율(초보 1.2 · 보통 1.0 · 숙련 0.8) | 이름 길이로 어림 (`basis: heuristic`) |
| `get_available_slots` | 이번 요청에서 사용자가 준 가용시간 | 빈 목록 — 평일 저녁을 지어내지 않는다 |
| `get_goal_catalog` | 목표 카탈로그 `services/goal_catalog.py` (담당 B) | 인기 목표 |
| `search_contests` | `contests` 테이블 (담당 D 의 `contest_repository`) | 빈 목록 |

커리큘럼의 `standard_minutes` 는 팀 추정치이고 `verified=false` 다 — 공식 출제기준 원문과 대조한 뒤 다음 번호 마이그레이션으로 `verified=true` 로 바꾼다.
세 시험 밖의 목표(토익·컴활 등)는 아직 커리큘럼이 없어 에이전트가 단위를 '추정'으로 표시한다.

응답의 `source` 로 결과가 어디서 왔는지 알 수 있다 — `agent` / `partial` / `template`.

#### 실측 (2026-09-24, Codyssey 게이트웨이, 정보처리기사 필기)

| 모델 | 결과 | 걸린 시간 | 학습 단위 | 도구 호출 |
|---|---|---|---|---|
| claude-sonnet-4 | `agent` | 41~46초 | 10~24개 | 8회 |
| claude-haiku-4 | `agent` | 33초 | 12개 | 14회 |

커리큘럼 DB 연결 후 (2026-09-26, claude-sonnet-4)

| 목표 | 결과 | 걸린 시간 | 학습 단위 | 추정 단위 | 모델 호출 |
|---|---|---|---|---|---|
| SQLD (단위 수 제한 전) | `template` / `agent` | 60초 초과 / 39초 | — / 33개 | — / 0 | 3회 |
| SQLD | `agent` | 31~35초 | 18~25개 | 0 | 2회 |
| 정보처리기사 필기 | `agent` | 28초 | 23개 | 0 | 2회 |

묶기 규칙(합 120분 이하)은 프롬프트로만 지킨다 — 실측에서 150분어치를 90분 단위 하나로 묶은 경우가 있었다.

최종 JSON 을 쓰는 마지막 호출 하나가 **약 24초**라서, 처음 명세의 "호출당 20초"로는 거의 항상 템플릿으로 떨어졌다.
그래서 시간 제한을 에이전트 전체 60초로 바꾸고 화면에 진행 단계를 보여준다.

#### 진행 표시 — `POST /plan/decompose/stream`

60초를 멈춘 화면으로 기다리게 할 수 없어서, 에이전트가 **실제로 한 일**을 한 줄(JSON)씩 보낸다.
타이머로 단계를 지어내지 않는다.

```
0.3s  {"type": "start", "budget_seconds": 60}
1.1s  {"type": "thinking", "step": 1}
6.6s  {"type": "tool", "name": "search_curriculum"}
 ...
45.6s {"type": "done", "source": "agent"}
45.6s {"type": "result", "result": {...}}      ← 항상 마지막 줄
```

화면: `frontend/components/PlanBuilder.js` (일정 탭 → 학습 계획 만들기).
`TestClient` 는 응답을 다 모아서 돌려주므로 시간 간격은 실제 서버(uvicorn)로 확인해야 한다.

### 스케줄 배치 엔진 (`FR-PLAN-03`)

`services/scheduler.py` — 난수를 쓰지 않으므로 같은 입력이면 항상 같은 결과.

지키는 규칙
- 선행 단위가 끝난 뒤에만 시작
- 하루 최대 **3블록**
- 블록 사이 최소 **10분** 휴식 (단위가 최대 120분이므로 연속 2시간을 넘지 않는다)
- 마감일 초과 금지 — 못 넣은 것은 `unplaced` 로 남긴다. **조용히 버리지 않는다**
- 고정 블록(완료·수동 이동)은 비켜서 배치

### 규칙 검증기

`services/validator.py` — AI 품질 평가의 **"일정 실현 가능성 100%"** 를 재는 도구다.

잡아내는 위반 5종: `deadline_exceeded` · `overlap` · `prerequisite_violation` ·
`daily_limit_exceeded` · `continuous_limit_exceeded`

### API

| 메서드 | 경로 | 기능 |
|---|---|---|
| POST | `/plan/decompose` | 목표 → 학습 단위 (`FR-PLAN-02`) |
| POST | `/plan/decompose/stream` | 위와 같고 진행 단계를 줄 단위로 흘려보냄 (NDJSON) |
| POST | `/plan/schedule` | 학습 단위 → 블록 배치 (`FR-PLAN-03`) |
| POST | `/plan/reschedule` | 야간 재조정 (`FR-PLAN-06`) |
| POST | `/plan/validate` | 규칙 위반 검사 |
| POST | `/plan/save` | 계획 확정·저장 — 저장 전 규칙 검증 한 번 더, 어기면 400. 다른 목표 일정과 겹쳐도 400, 진행 중 목표가 이미 2개면 409 (로그인) |
| GET | `/plan/active` | 진행 중 계획 전부 `{plans, max_plans}` — 목표는 동시에 최대 2개 (`FR-GOAL-07`, 로그인) |
| GET | `/plan/current` | 가장 최근 계획 하나, 없으면 `null` (예전 화면 호환, 로그인) |
| POST | `/plan/{id}/archive` | 목표 끝내기 — 보관, 학습 기록은 남음 (로그인) |
| POST | `/plan/{id}/place-unplaced` | 미배치 단위(블록 없는 단위)를 오늘 이후 빈 시간에 넣어 보기. 놓인 블록은 안 움직임, 직접 지운 단위는 제외 (`FR-PLAN-04`, 로그인) |
| POST | `/study/sessions` | 학습 세션 저장 + 본인 블록 완료 (`FR-STUDY-01/02`, 로그인) |
| GET | `/study/stats` | 내 누적·주간·연속·레벨 + 이번 주 달성률 — 저장된 기록 기준 (`FR-STUDY-03/04`, 로그인) |
| POST | `/study/stats` | 받은 기록으로 계산만 (DB 없이 시험용) |
| DELETE | `/study/blocks/{id}/done` | 완료 취소 — 24시간 안에만. 공부한 시간 기록은 남긴다 (`FR-STUDY-02`, 로그인) |
| GET | `/study/notes` | 학습 메모를 목표별로 모아보기, 끝낸 목표 포함 (`FR-STUDY-05`, 로그인) |
| POST | `/plan/scope` | 공부량이 기한까지 가용시간의 1.5배를 넘으면 범위 축소안(뺄 단위·늘릴 기한) (`FR-PLAN-02`) |
| GET | `/plan/changes` | 최근 7일 재조정 내역 + 3일 연속 밀림 여부 (`FR-PLAN-07`, 로그인) |
| POST | `/plan/changes/{id}/undo` | 가장 최근 재조정 되돌리기 — 한 번만 (`FR-PLAN-06`, 로그인) |
| POST | `/plan/replan-now` | 내 계획만 지금 재조정 — 03:00 을 기다리지 않고 확인할 때 (로그인) |
| POST | `/plan/nightly` | 전체 야간 재조정. 로그인 대신 `X-Batch-Key` 헤더 = `.env` 의 `BATCH_SECRET` (매일 03:00). 바로 202 로 답하고 뒤에서 돈다, 실행 중이면 409 |
| PATCH | `/plan/blocks/{id}` | 블록 옮기기 — 규칙에 걸리면 `applied:false` + 위반 목록, `force:true` 로 강행 (`FR-PLAN-05`, 로그인) |
| DELETE | `/plan/blocks/{id}` | 블록 지우기 — 완료한 블록은 못 지운다 (로그인) |

계획 만들기(`decompose`·`schedule`·`validate`)는 로그인 없이 된다 — 비회원도 써 보고 가입하게. 저장부터 로그인.
학습 분해를 부르면 `ai_call_logs` 에 한 줄 남는다 (기능·모델·결과 출처·도구 횟수·걸린 시간). DB 가 없거나 기록이 실패해도 계획 만들기는 막지 않는다.

**시간대** — 배치 엔진·API 는 시간대 없는 한국 시각(`2026-10-05T19:00:00`)을 쓰고, DB 에는 `+09:00` 을 붙여 저장한다 (`services/plan_store.py`).
**프론트 토큰** — `frontend/lib/api.js` 가 `localStorage['sp_access_token']` 을 모든 요청의 `Authorization` 헤더로 붙인다. 로그인 화면은 로그인 성공 시 여기에 `access_token` 을 넣으면 된다.

### 야간 재조정 · 변경 내역 · 블록 편집 (`services/replan.py`)

`FR-PLAN-06` 은 무인 실행이라 사용자가 중단시킬 수 없다. 그래서 **실패하면 기존 일정을 그대로 둔다** — 아침에 빈 일정표를 보는 상황이 가장 나쁘다.

| 규칙 | 구현 |
|---|---|
| 무엇을 다시 놓나 | 지난 미완료 블록 **+ 그 단원에 (간접적으로라도) 기대는 뒤 블록** (`scheduler.blocks_to_redo`). 지난 블록만 앞으로 옮기면 선행 순서가 뒤집힌다 |
| 건드리지 않는 것 | 완료 블록, 직접 옮긴 블록(`locked`) |
| 어디에 놓나 | `build_schedule` 그대로 (LLM 미사용). 오늘 빈 시간이 이미 시작됐으면 내일부터 |
| 블록 id | 그대로 두고 시각만 바꾼다 — 학습 기록·변경 내역이 같은 블록을 계속 가리키게 |
| 검증 | 이번 재조정으로 **새로 생긴** 위반이 하나라도 있으면 아무것도 바꾸지 않는다 |
| 중간 실패 | 이미 바꾼 블록을 원래대로 돌린다 (Supabase REST 에 트랜잭션이 없어서) |
| 자리가 없으면 | 원래 자리에 두고 `unplaced` 로 기록 — 조용히 버리지 않는다 |
| 사유 | 블록마다 규칙 문구. 요약 한 줄은 `claude-haiku-4` (15초), 실패하거나 책망하는 말이 섞이면 규칙 문구 |
| 되돌리기 | 가장 최근 재조정만, 한 번만. 그사이 끝냈거나 직접 옮긴 블록은 두고 나머지만 |
| 기한 조정 제안 | 블록이 밀린 날이 3일 연속이면 `suggest_extension` |
| 배치 전체 | 사용자별 순차 실행, 한 사람 실패해도 다음 사람 계속. 결과는 `batch_runs` (관리자 로그). 요청에는 바로 202 — Make 시간 제한에 안 걸리게 |
| 기한이 지난 계획 | 건너뛴다 — 옮길 자리가 없는데 날마다 같은 기록만 쌓이므로 |

**목표 2개 (`FR-GOAL-07`)** — 진행 중인 계획은 목표마다 하나, 최대 2개 (`schemas.goal.MAX_ACTIVE_GOALS`).
두 목표는 같은 빈 시간을 나눠 쓰므로 **배치(`/plan/schedule`, 로그인 시)·저장·야간 재조정·블록 옮기기 모두 다른 목표의 블록을 고정 블록으로 보고 피한다** (하루 3블록 상한도 두 목표 합산).
다른 목표 블록은 단위 id 앞에 계획 id 를 붙여 넘긴다 — 두 계획의 단위 id 가 같으면(`tpl-01`) 배치 엔진이 이미 놓인 단위로 착각한다.
변경 내역·되돌리기·기한 조정 제안은 목표별, 주간 달성률은 두 목표 합산.

**블록 직접 편집 (`FR-PLAN-05`)** — 옮긴 블록은 `locked` 가 되어 재조정에서 빠진다. 이번 이동으로 새로 생긴 위반만 본다.
겹침·기한 초과는 강행할 수 없고, 선행 순서·하루 상한은 경고 후 사용자가 강행을 고를 수 있다.

**03:00 실행** — `POST /plan/nightly` 를 Make(또는 cron)가 부른다. 헤더 `X-Batch-Key: <BATCH_SECRET>`. 스케줄 연결은 담당 E.
상태 없는 `/plan/reschedule` 도 남아 있다 — 예외가 나면 받은 블록을 그대로 돌려준다.

### 테스트

```bash
pytest -q       # 전체 237개 (C 담당 124개)
```

| 파일 | 확인하는 것 |
|---|---|
| `tests/test_plan_store.py` | 계획 저장·재조회, 이전 계획 보관, 규칙 위반 저장 거부, 블록 저장 실패 시 계획 롤백, 본인 블록만 완료, 5분 미만 미저장, DB 기준 통계, AI 호출 기록, DB 없이도 분해, 한국 시각 왕복 |
| `tests/test_agent_tools.py` | 커리큘럼 시드(009 SQL 을 그대로 읽어 검사), 목표 id·이름으로 찾기, 없는 목표 안내, DB 없어도 안 멈춤, 목표 안에서만 시간 추정·수준 배율, 사용자 가용시간 전달, B 카탈로그·D 공모전 사용 |
| `tests/test_multiplan.py` | 목표 2개: 두 번째 목표가 첫 목표 블록을 피해 놓이는지, 겹치는 일정 저장 거부, 세 번째 목표 409·같은 목표 교체, 목표 끝내기, 야간 재조정이 다른 목표와 안 겹치는지, 목표별 변경 내역·되돌리기, 먼저 만든 목표의 블록 편집, 달성률 합산 |
| `tests/test_replan.py` | 야간 재조정(뒤 블록 함께 밀기, 완료·고정 블록 유지, 자리 없음, 검증 실패·중간 실패 시 원상 유지), 배치 키·관리자 로그, 책망하는 AI 요약 거르기, 변경 내역 7일·되돌리기 1회, 3일 연속 제안, 블록 옮기기(경고·강행·겹침 거부)·지우기, 완료 취소 24시간, 주간 달성률, 범위 축소안이 실제로 다 들어가는지 |
| `tests/fake_supabase.py` | (도구) 테스트용 가짜 Supabase — 다른 파트도 `get_db` 에 끼워 쓰면 된다 |
| `tests/test_decomposer.py` | 도구 루프, 결과 한 메시지로 반환, `save_plan` 미실행, 오늘 날짜, 남은 시간만 주기, 타임아웃·예산 소진·스키마 실패 폴백, 반복 상한, 스트림 마지막 줄 |
| `tests/test_scheduler.py` | 결정론성, 규칙 준수, 휴식일, 선행 관계, 미배치 처리, 재조정 |
| `tests/test_validator.py` | 위반 5종을 실제로 잡아내는지 |
| `tests/test_aggregator.py` | 5분 미만 제외, 스트릭, 레벨 구간, 주 경계 |

`test_같은_입력이면_같은_결과가_나온다` 와 `test_배치_결과가_규칙을_어기지_않는다` 가
발표에서 "일정 실현 가능성 100%"를 주장할 근거다.

---

## 공모전·개인화 (담당 D)

위비티 수신 확인은 이용 허락이 아니다. 새 수집은 기본 비활성화(`WEVITY_CRAWLING_ENABLED=false`)이며, 실행 전에 출처 정책을 운영자가 확인해야 한다. 저장 항목은 목록의 **제목·공고 링크·출처**로 한정하고, 상세 페이지는 요청하지 않는다. 2026-09-28에 기존 방식으로 저장된 메타데이터는 이 변경에서 삭제하지 않는다. 화면에는 위비티 공고의 제목·출처·원문 링크만 표시한다.

| 항목 | 내용 |
|---|---|
| 수집 범위 | 사용자 지정 위비티 과학/공학(cidx=22) 목록 상위 **20건**. 다른 분야·페이지를 지정해도 전체 최대 20건 |
| 저장하는 것 | 제목·위비티 공고 링크·출처. 기존 `contests` 스키마 호환을 위한 빈 필드만 함께 저장. 포스터·원문·주최·분야·기간·응모대상은 새로 수집하지 않음 |
| 실행 조건 | 기본 비활성화. `WEVITY_CRAWLING_ENABLED=true`와 API의 `BATCH_SECRET`가 둘 다 필요 |
| 요청 간격 | 여러 목록을 요청할 때 사이에 3초 |
| 기록 | `batch_runs` (`job_name=contest.collect`) — 성공·부분 성공·실패와 건수 |
| 수동 실행 | `cd backend` 후 `python -m scripts.collect_contests --dry-run` (활성화한 경우만) |
| 매일 실행 | `POST /contests/collect` + `X-Batch-Key`. GitHub Actions에서 별도 스위치로 관리 |

- 데이터베이스에는 `migrations/016_wevity_link_only.sql`이 필요하다. 016은 제목·링크 전용 공고에 마감일이 없을 수 있게 한다. 날짜 없는 공고는 사용자가 원문에서 마감일을 확인해 직접 입력한 뒤 준비 기간을 계산한다. 입력값은 계산 단계에서 DB에 저장하지 않고, 사용자가 일정을 확정하면 계획 정보로 저장된다.
- `GET /contests/recommendations?tags=AI`는 저장된 공고 최대 20건의 **제목과 관심 키워드만** Codyssey Claude Haiku 게이트웨이에 보내 관련성을 판단한다. 응답의 공고 ID·점수를 검증한 뒤 최대 5건을 재랭킹한다. Claude 키가 없거나 호출·응답 검증이 실패하면 제목 키워드 일치로 복구한다. Claude가 정상적으로 빈 결과를 주면 관련 공고가 없다고 안내한다. 위비티 추천의 자격 점수는 검증되지 않은 중립값이며 지원 자격을 단정하지 않는다.
- 이 방식은 **임베딩·pgvector RAG가 아니다**. 교육 과정에서 제공하는 Claude Messages 게이트웨이에 임베딩 API가 없어 `FR-CONT-02`의 원래 색인 요건은 충족하지 못한다. 이전 실험용 `017_contest_title_vectors.sql` 파일은 호환성 기록으로 남겨 두되 적용할 필요가 없다. 관리자 화면의 기존 색인 상태도 과거 데이터 점검용이다.
- `.github/workflows/contest-jobs.yml`은 기본 비활성화다. 추천만 운영하려면 배포 API의 `BATCH_SECRET`과 GitHub Secrets `BATCH_SECRET`·`STUDYPACE_API_BASE`를 설정하고 Repository variable `CONTEST_RECOMMENDATIONS_ENABLED=true`로 켠다. 수집은 별도 `CONTEST_COLLECTION_ENABLED=true`에 더해 배포 API의 `WEVITY_CRAWLING_ENABLED=true`가 필요하다. 출처 정책 확인 전에는 수집을 켜지 않는다. API는 202로 즉시 응답하므로 완료 여부는 `batch_runs`에서 확인한다.
- 계정별 관심 태그는 `PUT /memories/interest-tags`, 조회는 `GET /memories`, 항목/전체 즉시 삭제는 `DELETE /memories/{id}` / `DELETE /memories`다. 학습 기록을 새로 저장하면 최근 4주 기록으로 선호 학습 시간대·노력 편차·완료율을 갱신한다. 삭제한 학습 통계도 이후 새 기록이 생기면 다시 계산될 수 있다. `POST /contests/{id}/feedback`은 당시 점수를 함께 저장하고 '안 맞음' 기억의 영향은 4주마다 절반으로 줄인다. 모든 계정 데이터는 서버에서 토큰 사용자 ID로 제한한다.
- 예전 92건의 저장 자료를 삭제하거나 배포 DB 마이그레이션을 실행하지 않았다. 팀이 자료 보관·정리와 운영 정책을 결정해야 한다.

## 남은 작업

- [x] `services/agent_tools.py` 의 목업 데이터를 DB·팀 서비스 조회로 교체 (커리큘럼 `curriculum_units`, 카탈로그 B, 공모전 D, 가용시간은 요청 값)
- [ ] 커리큘럼 공식 원문 대조 후 `verified=true` · 다른 목표(컴활·토익 등) 커리큘럼 추가
- [ ] 구글 캘린더 연동 (`FR-PLAN-01`) — `get_available_slots` 도구 안쪽
- [x] AI 호출 로그 저장 (`FR-ADMIN-02` 대시보드 근거) — `ai_call_logs`
- [x] 프론트 `/schedule` 에서 계획 만들기(분해 → 배치 → 검증)를 실제 API로 호출
- [x] 프론트 `/schedule` 주·월 달력과 날짜별 블록, `/study` 타이머·메모·집계를 목업에서 API 로 전환
  (`components/PlanCalendar.js`, `components/StudyTimer.js` — 닫아도 이어하기, 30분 무조작 자동 멈춤, 오프라인 저장 후 재전송)
- [x] 블록 완료 취소 (24시간 이내, `FR-STUDY-02`) · 주간 달성률 (`FR-STUDY-03`) · 1.5배 초과 시 범위 축소안 (`FR-PLAN-02`)
- [x] 블록 옮기기·지우기·끌어다 놓기 (`FR-PLAN-05`) · 변경 내역·되돌리기 (`FR-PLAN-07`)
- [x] 계획 확정(`save_plan`) — 사용자 확인 버튼 + 저장 API (`/plan/save`, `/plan/current`)
- [x] 학습 기록·집계를 DB 로 (`/study/sessions`, `GET /study/stats`)
- [ ] 로그인 연결 후 실제 계정으로 저장→조회→학습 기록 확인 (담당 E 의 로그인 화면이 선행)
- [x] 야간 재조정을 저장된 계획에 적용 (`/plan/nightly`, `/plan/replan-now`)
- [ ] 03:00 에 `/plan/nightly` 부르기 — Make 시나리오 또는 cron + `BATCH_SECRET` 설정 (담당 E)
