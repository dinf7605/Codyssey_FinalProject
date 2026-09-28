-- 담당: E. 이유: 관리자용 학습 분해 AI 요청 성공/실패 및 토큰 통계.
-- 015 번호는 팀 채널에서 사용을 알리고 확정한 뒤 담당 C가 공용 DB에 적용한다.
-- 기존 ai_call_logs·사용자 테이블은 변경하지 않는다. 사용자 식별자를 수집하지 않는 전역 운영 로그다.
-- 공용 DB 담당자 검토 후 적용. 적용 전 AI_REQUEST_METRICS_ENABLED는 설정하지 않는다.
begin;
create table if not exists public.ai_request_logs (
    id bigint generated always as identity primary key,
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
    created_at timestamptz not null default now(),
    unique (run_id, attempt_no),
    check ((succeeded and error_kind is null) or (not succeeded and error_kind is not null))
);
-- 개인 DB에 만든 UUID 버전 등과 혼동하면 중단한다. 기존 테이블을 자동 변환하지 않는다.
do $$
begin
    if not exists (
        select 1 from pg_attribute
        where attrelid = 'public.ai_request_logs'::regclass
          and attname = 'id' and not attisdropped
          and atttypid = 'bigint'::regtype and attidentity = 'a'
    ) then
        raise exception 'ai_request_logs.id must be bigint generated always as identity; review the target DB schema';
    end if;
end;
$$;
create index if not exists ai_request_logs_created_idx on public.ai_request_logs (created_at desc);
alter table public.ai_request_logs enable row level security;
revoke all privileges on table public.ai_request_logs from public, anon, authenticated;
grant select, insert on table public.ai_request_logs to service_role;
revoke all privileges on sequence public.ai_request_logs_id_seq from public, anon, authenticated;
grant usage, select on sequence public.ai_request_logs_id_seq to service_role;
comment on table public.ai_request_logs is '학습 분해 Messages 요청 기록. 프롬프트·응답 본문·사용자 식별자는 저장하지 않음. 비용 및 청구 내역 아님.';
commit;
