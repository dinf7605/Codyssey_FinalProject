-- 운영 모니터링 — 서버 오류 기록 · 알림 워커 생존 신호 (10-07, 평가 #3 보완)
--
-- error_logs          API 의 5xx 응답 · 처리되지 않은 예외, 알림 워커 작업 실패를 남긴다
--                     (backend/utils/error_monitor.py · workers/notification_worker.py).
--                     사용자 식별자는 넣지 않는다. 경로는 '/plan/{plan_id}' 같은 틀로, 메시지는 300자로 자르고 이메일·긴 숫자를 가린다.
-- service_heartbeats  알림 워커가 1분마다 '살아 있음'을 남긴다. GET /health/ready 가 10분 넘게 소식이 없으면 stale 로 본다.
--
-- 가동률은 DB 가 아니라 GitHub Actions(uptime.yml) 가 밖에서 15분마다 점검한 기록으로 계산한다 — docs/operations.md
-- 적용 전에도 서비스는 그대로 돈다. 기록만 남지 않는다 (쓰기 실패는 무시).

begin;

create table if not exists public.error_logs (
    id bigint generated always as identity primary key,
    occurred_at timestamptz not null default now(),
    source text not null check (source in ('api', 'worker')),
    method text,
    route text not null,
    status_code integer,
    error_type text not null,
    message text,
    request_id text
);

create index if not exists error_logs_occurred_idx on public.error_logs (occurred_at desc);

create table if not exists public.service_heartbeats (
    service text primary key,
    beat_at timestamptz not null default now(),
    started_at timestamptz,
    version text
);

-- 서버(Service Role)만 읽고 쓴다. 정책을 두지 않아 anon·로그인 사용자는 접근할 수 없다.
alter table public.error_logs enable row level security;
alter table public.service_heartbeats enable row level security;

commit;
