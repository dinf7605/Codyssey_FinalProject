# 운영 모니터링 · 장애 대응 · 배포 후 자동 복구

> 평가 항목 #3 보완 (10-07). 지적: *"운영 무중단 상태를 입증할 가동률·오류 로그 미제출 — 운영 모니터링(가동시간·오류/예외 로그 요약)과 배포 후 자동 복구 절차를 제출"*.
> 이 문서가 그 제출물이다. 숫자는 `backend/scripts/ops_report.py` 로 언제든 다시 뽑는다 (7절).

## 1. 한눈에

| 무엇을 | 어떻게 재나 | 어디서 보나 |
|---|---|---|
| **가동률 (가동시간)** | GitHub Actions `uptime.yml` 이 **15분마다 밖에서** 프론트 · 백엔드 준비 상태 · DB 읽기 API · 알림 워커를 점검. 실행 기록 = 가동률 원장 | 관리자 화면 **'운영 상태'** · [Actions › Uptime monitor](https://github.com/dinf7605/Codyssey_FinalProject/actions/workflows/uptime.yml) · `ops_report.py` |
| **장애 이력** | 점검이 실패하면 `ops-incident` 이슈를 자동으로 열고, 다시 정상이면 장애 시간을 적고 자동으로 닫는다 | GitHub Issues (`ops-incident` 라벨) |
| **오류 · 예외 로그** | API 의 5xx 응답 · 처리되지 않은 예외, 알림 워커 작업 실패를 `error_logs` 에 남긴다 (서버 로그에는 traceback 까지) | 관리자 화면 '운영 상태' · Railway Logs · `ops_report.py --with-db` |
| **알림 워커 생존** | 워커가 1분마다 `service_heartbeats` 에 신호. 10분 넘게 없으면 stale | `/health/ready` · 외부 점검 |
| **배포 후 확인** | `deploy-check.yml` — push 하면 새 버전(커밋)이 실제로 떴는지 기다린 뒤 핵심 경로 점검. 실패하면 `deploy-failure` 이슈 | Actions › Deploy check · Issues |
| **정해진 시각 작업** | 공고 수집 05:00 · 추천 월 09:00 · 야간 재조정 03:00 (워크플로) + 실행 결과 `batch_runs` | Actions · 관리자 화면 'DB 현황' |

```mermaid
flowchart LR
  gha["GitHub Actions<br/>uptime.yml (15분)<br/>deploy-check.yml (push)"] -->|HTTPS| web["프론트 (Vercel)"]
  gha -->|/health/ready · /contests| api["백엔드 API (Railway)"]
  api -->|DB 읽기| db[("Supabase")]
  worker["알림 워커 (Railway)"] -->|1분마다 생존 신호| db
  api -->|5xx · 예외| db
  worker -->|작업 실패| db
  gha -->|실패 · 복구| issue["GitHub Issues<br/>ops-incident · deploy-failure"]
  admin["관리자 화면 '운영 상태'"] -->|GET /admin/ops| api
  api -->|실행 기록 (30분 저장)| gha
```

가동률을 서버 **밖**에서 재는 이유 — 서버가 죽으면 스스로는 "죽었다"는 기록을 못 남긴다. 외부 점검 기록은 서버 · DB 장애와 상관없이 남는다.

## 2. 가동률 — 외부 점검 (`.github/workflows/uptime.yml`)

| 점검 | 정상 조건 | 왜 |
|---|---|---|
| 프론트 첫 화면 | 200 + 본문에 `StudyPace` | Vercel 배포 · 도메인 |
| 백엔드 `/health/ready` | 200 + `"db":"ok"` | **DB 를 실제로 읽는다.** 10차 점검에서 `/health` 는 200 인데 DB 키가 없어 모든 요청이 503 이었다 |
| `/contests?limit=1` | 200 | 화면이 쓰는 DB 읽기 API |
| 알림 워커 | `/health/ready` 의 `worker` 가 `stale` 이 아님 | 워커는 HTTP 가 없어 생존 신호로 본다 |

- **주기** 15분 (`7,22,37,52 * * * *`). 한 점검 안에서 20초 간격으로 3번까지 다시 본다 — 순간 끊김을 장애로 세지 않는다
- **가동률** = 정상 점검 ÷ 끝난 점검 × 100. 취소 · 건너뜀은 점검이 아니라서 뺀다 (`services/ops_monitor.uptime_from_runs`)
- **장애 구간** = 연달아 실패한 점검의 첫 실패 ~ 다음 정상 점검. 15분 간격이라 실제보다 최대 15분 길게 잡힌다 (보수적)
- 각 실행의 **Summary** 탭에 점검 표(HTTP 코드 · 응답 시간)가 남는다
- 저장소가 공개라 Actions 비용이 들지 않는다. 관리자 화면은 GitHub API 를 30분마다 한 번만 읽는다 (비로그인 한도 시간당 60회)

## 3. 오류 · 예외 로그

| 어디서 | 무엇을 | 구현 |
|---|---|---|
| API | 5xx 응답 전부 · 처리되지 않은 예외 | `backend/utils/error_monitor.py` (순수 ASGI 미들웨어) |
| 알림 워커 | 작업(시작 전 알림 등) 실패 | `workers/notification_worker.py` `_safe` |

- **남기는 곳 두 군데** — ① 서버 로그(Railway › Logs): 한 줄 요약, 예외는 traceback 까지 ② `error_logs` 테이블: 경로 틀 · 상태 코드 · 오류 유형 · 메시지 · 요청 번호
- **요청 번호** — 모든 응답에 `X-Request-ID` 헤더. 처리되지 않은 예외는 사용자에게 traceback 대신 *"서버에서 오류가 났습니다"* + `request_id` 만 돌려준다. 사용자가 오류를 알려 주면 이 번호로 두 로그를 찾는다
- **개인정보** — 사용자 id 를 넣지 않는다. 경로는 `/plan/{plan_id}` 같은 **틀**로, 메시지는 이메일 · UUID · 6자리 넘는 숫자를 가리고 300자로 자른다 (`ops_monitor.scrub`). DB 현황 목록에는 메시지 열을 보내지 않는다
- **폭주 방지** — DB 에는 분당 30건까지만 쓴다 (DB 장애 때 기록 시도가 장애를 키우지 않게). 서버 로그에는 모두 남는다
- **기록 실패는 무시** — 모니터링 장애로 본 기능을 막지 않는다. DB 쓰기는 응답을 붙잡지 않게 스레드로 보낸다
- **요약** — 관리자 화면 '운영 상태'(최근 7일 날짜별 건수 · 유형 · 최근 5건), `ops_report.py --with-db`(경로 · 유형 상위 5, 최근 10건)

## 4. 배포 후 자동 복구

여러 겹으로 둔다. 사람이 없어도 1~3 이 서비스를 지키고, 4~5 가 사람을 부른다.

| 겹 | 상황 | 자동으로 일어나는 일 | 설정 |
|---|---|---|---|
| 1 | 새 백엔드 배포가 뜨지 않거나 DB 를 못 읽음 | Railway 가 `/health/ready` 를 120초 안에 통과한 배포에만 트래픽을 넘긴다 → **실패한 배포는 버려지고 직전 정상 버전이 계속 서비스** (무중단) | `backend/railway.api.json` `healthcheckPath` |
| 2 | 실행 중 프로세스가 죽음 | Railway 가 다시 띄운다 — API 는 실패 종료 시 10번까지, 워커는 항상 | `restartPolicyType` `ON_FAILURE` · `ALWAYS` |
| 3 | 프론트 빌드 실패 | Vercel 이 실패한 빌드를 올리지 않는다 → 직전 배포 유지 | Vercel 기본 |
| 4 | 배포 뒤 새 버전이 15분 안에 안 뜸 · 핵심 경로 실패 | `deploy-check.yml` 실패 → `deploy-failure` 이슈 (커밋 · 실패 항목 · 롤백 방법). 다음 배포가 정상이면 자동으로 닫힘 | `.github/workflows/deploy-check.yml` |
| 5 | 운영 중 장애 (외부 점검 실패) | `ops-incident` 이슈를 열고, 실패가 이어지면 댓글. (선택) **두 번 연속(30분) 백엔드 실패면 Railway 에 재배포를 한 번 요청**. 복구되면 장애 시간을 적고 자동으로 닫음 | `uptime.yml` · secrets (6-3) |

새 버전 확인은 `GET /health` 의 `version`(Railway 가 넣어 주는 `RAILWAY_GIT_COMMIT_SHA` 앞 7자리)을 push 한 커밋과 비교한다. 백엔드를 건드리지 않은 push 는 버전을 기다리지 않고 점검만 한다.

## 5. 장애 대응

| 증상 (이슈 · 화면) | 먼저 볼 것 | 조치 |
|---|---|---|
| 프론트 첫 화면 실패 | Vercel › Deployments 최근 배포 상태 | 빌드 실패면 직전 배포 유지 중 — 원인 수정 후 push. 화면이 깨졌으면 **롤백** |
| `/health/ready` 503 · `db: not_configured` | Railway › API › Variables | Supabase 키(`SUPABASE_URL` · `SUPABASE_SERVICE_ROLE_KEY`) 다시 넣기 → 자동 재배포 |
| `/health/ready` 503 · `db: error` | Supabase 상태 페이지 · Railway Logs | Supabase 장애면 기다림(복구되면 이슈 자동 종료). 우리 쪽 오류면 Logs 의 `[오류]` 줄 · `error_logs` |
| 백엔드 응답 없음 (HTTP 000 · 5xx) | Railway › API › Deployments · Logs | 프로세스 재시작 확인. 멈춰 있으면 **Restart**. 최근 배포 직후면 **롤백** |
| 알림 워커 `stale` | Railway › 워커 › Logs (`[알림 워커]` 줄) | 오류 반복이면 원인 수정. 멈춰 있으면 **Restart** |
| `deploy-failure` 이슈 | 이슈의 실행 기록 · Railway 배포 로그 | 새 버전이 안 떴으면 이전 버전이 서비스 중 — 원인 수정 후 push. 떴는데 점검 실패면 **롤백** |
| 사용자 오류 문의 (요청 번호) | `error_logs` 에서 `request_id` · Railway Logs 검색 | 재현 → 수정 → 테스트 → push |

**롤백** — Railway › 서비스 › Deployments › 직전 정상 배포 › **Redeploy** (또는 Rollback). Vercel › Deployments › 직전 배포 › **Promote to Production** (Instant Rollback). 그다음 원인을 고친 커밋을 push 하면 `deploy-check.yml` 이 다시 확인한다.

## 6. 한 번만 하는 설정

### 6-1. DB (팀 리드)

Supabase SQL Editor 에서 [`backend/migrations/020_ops_monitoring.sql`](../backend/migrations/020_ops_monitoring.sql) 실행 — `error_logs` · `service_heartbeats`. 적용 전에도 서비스는 그대로 돌고 기록만 남지 않는다.

### 6-2. Railway (배포 담당)

API · 워커 서비스 각각 **Settings › Config-as-code › Railway Config File** 에 경로를 넣는다 (저장소 루트 기준).

| 서비스 | 파일 | 내용 |
|---|---|---|
| API | `/backend/railway.api.json` | 시작 명령 · 헬스체크 `/health/ready` (120초) · 재시작 ON_FAILURE 10번 |
| 알림 워커 | `/backend/railway.worker.json` | 시작 명령 · 재시작 ALWAYS (헬스체크 없음 — HTTP 서버가 아님) |

> 같은 값을 화면에서 직접 넣어도 된다 (Settings › Deploy › Healthcheck Path · Restart Policy). **워커에 헬스체크를 넣지 않는다** — 넣으면 배포가 늘 실패한다.

### 6-3. 자동 재배포 켜기 (선택)

저장소 Settings › Secrets and variables › Actions 에 `RAILWAY_TOKEN`(Railway › Account › Tokens), `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_API_SERVICE_ID`(API 서비스 Settings 에 보이는 id). 없으면 이 단계만 건너뛴다.
Railway API 호출(`serviceInstanceRedeploy`)은 실제 장애 때만 실행되므로 미리 검증하지 못했다. 동작 여부는 장애 이슈에 남는 '자동 재배포 요청' 댓글의 응답으로 확인한다.

### 6-4. 주소를 바꾸면

저장소 variables `UPTIME_API_BASE` · `UPTIME_WEB_BASE` (없으면 현재 배포 주소가 기본값).

## 7. 측정 결과

### 7-1. 다시 뽑는 법

```bash
cd backend
python -m scripts.ops_report --days 7                                       # GitHub 기록 (가동률 · 장애 · 배포 확인 · 배치 · CI)
python -m scripts.ops_report --days 7 --with-db --out ../docs/ops-report.md   # + error_logs 요약 (.env 필요)
```

### 7-2. 10-07 기준 (모니터링 도입 시점)

`uptime.yml` · `deploy-check.yml` 은 이번 push 부터 기록이 쌓인다. 도입 전 운영 상태는 이미 돌던 워크플로 기록과 수동 점검으로 확인했다.

**정해진 시각 작업 · CI** (`ops_report.py --days 3`, 10-04 14:10 ~ 10-07 14:10 KST)

| 워크플로 | 실행 | 성공 | 실패 | 성공률 | 비고 |
|---|---|---|---|---|---|
| 공고 수집 · 추천 (`contest-jobs.yml`) | 5 | 4 | 1 | 80.0% | 실패 1건은 10-05 13:30 — 배포 직후 secret 이 백엔드가 아닌 주소를 가리킨 건(10차 점검). 고친 뒤 모두 성공 |
| 야간 재조정 03:00 (`plan-jobs.yml`) | 3 | 3 | 0 | 100% | |
| CI (`ci.yml`) | 10 | 10 | 0 | 100% | 테스트 · lint · build |

**배포 주소 수동 점검** (10-07 14:14 KST, 3초 간격 5회)

| 대상 | 결과 | 응답 시간 |
|---|---|---|
| 프론트 `/` | 200 × 5 | 0.09 ~ 0.76초 |
| 백엔드 `/health` | 200 × 5 | 0.21 ~ 0.38초 |
| `/contests?limit=1` (DB 읽기) | 200 × 5 | 0.52 ~ 0.65초 |

### 7-3. 제출 직전에 채울 것

- [ ] `ops_report.py --days 7 --with-db --out ../docs/ops-report.md` 실행 → 가동률 · 장애 이력 · 오류 요약을 [ops-report.md](ops-report.md) 로 저장
- [ ] 관리자 화면 '운영 상태' 캡처 → `docs/screens/17-admin-ops.jpg`
- [ ] 장애가 있었다면 `ops-incident` 이슈 링크와 원인 · 조치를 아래 표에

| 날짜 | 장애 | 길이 | 원인 | 조치 |
|---|---|---|---|---|
| | | | | |

## 8. 한계

- 외부 점검은 15분 간격이라 그보다 짧은 장애는 놓칠 수 있고, 장애 시간은 15분 단위로 잡힌다. GitHub 이 붐비면 스케줄이 몇 분 늦거나 드물게 건너뛴다 (건너뛴 회차는 가동률 계산에서 빠진다)
- GitHub Actions 자체 장애 시간에는 점검이 없다
- 오류 기록은 DB 에 남기므로 **DB 장애 중 오류는 Railway 로그에만** 남는다
- 이용자 화면(브라우저)에서 난 오류는 수집하지 않는다 — 서버 오류만 센다
- 자동 재배포(겹 5)는 secrets 를 넣어야 동작하고, 같은 장애에 한 번만 시도한다. 그래도 안 되면 사람이 5절대로 대응한다
