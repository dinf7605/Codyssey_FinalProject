# 관리자 AI 요청 통계

GET /admin/ai-request-metrics?day=YYYY-MM-DD (관리자 전용, 한국 시간 하루)

- 기존 ai_call_logs 처리 통계와 별개로 ai_request_logs의 plan.decompose를 집계한다.
- 실패율 = succeeded=false 요청 / 저장된 전체 요청 × 100. 응답 내용 검증 실패율이나 계획 생성 실패율이 아니다.
- 요청 재시도는 각각 1건이다. API 키가 없어 호출하지 않은 실행은 요청 기록에 포함되지 않는다.
- 토큰은 입력/출력/캐시 생성/캐시 읽기를 나누어 합계와 값이 있는 요청 수를 표시한다. 누락은 0으로 추정하지 않는다.
- status: disabled(저장 비활성, DB 조회 생략), empty(기록 없음), ok, unavailable(조회 실패), limit_exceeded.
- AI_REQUEST_METRICS_ENABLED=0에서는 과거 통계도 조회하지 않는다. 서버 설정을 1로 바꾸기 전에는 DB를 읽지 않는다.
- 저장된 기록만 집계하므로 저장 실패나 비활성 기간의 사용량은 포함되지 않는다. 청구 비용이 아니다.
- 하루 20,000건, 최대 100회 조회로 제한. 페이지마다 정확한 건수와 중복 ID를 검사하며 불완전한 합계를 반환하지 않는다.
- 여러 페이지 조회는 DB 스냅샷이 아니다. 동시 변경 중 일부 경우는 감지할 수 없다. 현재 기록은 append-only 운영을 전제로 한다.
- 관리자 권한 확인과 각 화면 조회를 분리해 처리 기록 조회 실패가 공고 점검·요청 통계를 막지 않도록 한다.

## 적용 후 검증 (프로젝트 루트 PowerShell)

```powershell
Push-Location backend
python -m pytest tests/test_admin_request_summary.py tests/test_ai_request_metrics.py tests/test_decomposer.py -q
Pop-Location
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check
git status --short
```

공용 DB 변경, .env 수정, 커밋/푸시는 자동으로 수행하지 않는다.
실제 로그인 및 공용 DB 저장·조회 검증은 팀 연동 후 별도 수행한다.

## 팀 DB 기준 반영

- SQL: backend/migrations/015_ai_request_logs.sql (팀 채널에서 번호 확정 필요).
- id는 bigint identity이며 관리자 집계는 양의 정수 ID를 검증한다. run_id는 실행 간 구분용 UUID를 유지한다.
- 사용자 식별자 없는 전역 운영 로그이며 관리자 권한으로만 집계한다.
- 담당 C가 공용 DB 적용·이력·Advisors를 확인한 뒤 활성화한다. 개인 SQL Editor에서는 실행하지 않는다.
