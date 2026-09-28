-- 학습 분해의 실제 AI 요청 계측. 기존 ai_call_logs·사용자 테이블은 변경하지 않는다.
-- 공용 DB 담당자 검토 후 적용. 적용 전 AI_REQUEST_METRICS_ENABLED는 설정하지 않는다.
begin;
create table public.ai_request_logs (
    id uuid primary key,
    run_id uuid not null,
    attempt_no integer not null check (attempt_no > 0),
    feature text not null check (feature = 'plan.decompose'),
    model text not null,
    succeeded boolean not null,
    error_kind text check (error_kind in ('timeout', 'rate_limit', 'authentication', 'http_error', 'request_error')),
    outcome text not null check (outcome in ('agent', 'partial', 'template', 'error')),
    latency_ms integer not null check (latency_ms >= 0),
    input_tokens bigint check (input_tokens >= 0),
    output_tokens bigint check (output_tokens >= 0),
    cache_creation_input_tokens bigint check (cache_creation_input_tokens >= 0),
    cache_read_input_tokens bigint check (cache_read_input_tokens >= 0),
    created_at timestamptz not null,
    unique (run_id, attempt_no),
    check ((succeeded and error_kind is null) or (not succeeded and error_kind is not null))
);
create index ai_request_logs_created_idx on public.ai_request_logs (created_at desc);
alter table public.ai_request_logs enable row level security;
revoke all privileges on table public.ai_request_logs from public, anon, authenticated;
grant select, insert on table public.ai_request_logs to service_role;
comment on table public.ai_request_logs is '학습 분해 Messages 요청 기록. 프롬프트·응답 본문·사용자 식별자는 저장하지 않음. 비용 및 청구 내역 아님.';
commit;
