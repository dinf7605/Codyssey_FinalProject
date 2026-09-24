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
| 도구 | 6종 (`services/agent_tools.py`) | AI기능명세 1 |
| 최대 반복 | **5회** | 3회로는 검색→추정→배치 연계가 끊기고, 8회 이상은 결과 차이 없이 비용만 증가 |
| 모델 | `claude-sonnet-4` | 아래 실측 — haiku 보다 8초 느리지만 단위를 더 잘게 나누고 추정 표시가 정확 |
| 시간 제한 | **전체 60초** (호출당 아님) | NFR-PERF-01. 각 호출에는 남은 시간만 준다 |
| SDK 자동 재시도 | **끔** (`max_retries=0`) | 켜 두면 타임아웃마다 2번 더 기다려 2분을 넘긴다 |
| 스키마 강제 | 도구에 `strict: true` | 인자가 스키마를 반드시 통과 → 검증 실패 폴백 자체가 줄어든다 |
| 실패 시 | 1회 재시도 → 템플릿 대체 | AI기능명세 6 |
| 사용자 확인 필요 | `save_plan` | 되돌리기 어려운 동작은 에이전트가 직접 실행하지 않는다 |
| 오늘 날짜 | 프롬프트에 넣는다 | 안 넣었더니 모델이 2024~2025년 날짜로 빈 시간을 조회했다 |

응답의 `source` 로 결과가 어디서 왔는지 알 수 있다 — `agent` / `partial` / `template`.

#### 실측 (2026-09-24, Codyssey 게이트웨이, 정보처리기사 필기)

| 모델 | 결과 | 걸린 시간 | 학습 단위 | 도구 호출 |
|---|---|---|---|---|
| claude-sonnet-4 | `agent` | 41~46초 | 10~24개 | 8회 |
| claude-haiku-4 | `agent` | 33초 | 12개 | 14회 |

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
| POST | `/study/sessions` | 학습 세션 기록 (`FR-STUDY-01/02`) |
| POST | `/study/stats` | 누적·연속·레벨 집계 (`FR-STUDY-03/04`) |

### 야간 재조정이 실패해도 일정은 안 깨진다

`FR-PLAN-06` 은 무인 실행이라 사용자가 중단시킬 수 없다.
`routers/plan.py` 의 `/plan/reschedule` 은 예외가 나면 **받은 블록을 그대로 돌려준다.**
아침에 빈 일정표를 보는 상황이 가장 나쁘기 때문이다.

### 테스트

```bash
pytest -q       # C 담당 35개
```

| 파일 | 확인하는 것 |
|---|---|
| `tests/test_decomposer.py` | 도구 루프, 결과 한 메시지로 반환, `save_plan` 미실행, 오늘 날짜, 남은 시간만 주기, 타임아웃·예산 소진·스키마 실패 폴백, 반복 상한, 스트림 마지막 줄 |
| `tests/test_scheduler.py` | 결정론성, 규칙 준수, 휴식일, 선행 관계, 미배치 처리, 재조정 |
| `tests/test_validator.py` | 위반 5종을 실제로 잡아내는지 |
| `tests/test_aggregator.py` | 5분 미만 제외, 스트릭, 레벨 구간, 주 경계 |

`test_같은_입력이면_같은_결과가_나온다` 와 `test_배치_결과가_규칙을_어기지_않는다` 가
발표에서 "일정 실현 가능성 100%"를 주장할 근거다.

---

## 남은 작업

- [ ] `services/agent_tools.py` 의 목업 데이터를 Supabase 조회로 교체 (에이전트 코드는 그대로)
- [ ] 구글 캘린더 연동 (`FR-PLAN-01`) — `get_available_slots` 도구 안쪽
- [ ] AI 호출 로그 저장 (`FR-ADMIN-02` 대시보드 근거)
- [x] 프론트 `/schedule` 에서 계획 만들기(분해 → 배치 → 검증)를 실제 API로 호출
- [ ] 프론트 `/schedule` 의 주간·오늘 블록, `/study` 를 목업에서 API 로 전환 (저장소가 붙은 뒤)
- [ ] 계획 확정(`save_plan`) — 사용자 확인 버튼 + 저장 API
