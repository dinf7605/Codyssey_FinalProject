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

루트의 `.env.example` 을 복사해 `.env` 로 만들고 값을 채운다.
`ANTHROPIC_API_KEY` 가 비어 있으면 **AI를 호출하지 않고 표준 커리큘럼 템플릿으로 동작**한다.
키 없이도 로컬 개발이 가능하도록 일부러 그렇게 만들었다.

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
| 타임아웃 | 20초 | AI기능명세 6 |
| 스키마 강제 | 도구에 `strict: true` | 인자가 스키마를 반드시 통과 → 검증 실패 폴백 자체가 줄어든다 |
| 실패 시 | 1회 재시도 → 템플릿 대체 | AI기능명세 6 |
| 사용자 확인 필요 | `save_plan` | 되돌리기 어려운 동작은 에이전트가 직접 실행하지 않는다 |

응답의 `source` 로 결과가 어디서 왔는지 알 수 있다 — `agent` / `partial` / `template`.

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
pytest -q       # 24개
```

| 파일 | 확인하는 것 |
|---|---|
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
- [ ] 프론트 `/schedule` · `/study` 를 목업에서 이 API 호출로 전환
