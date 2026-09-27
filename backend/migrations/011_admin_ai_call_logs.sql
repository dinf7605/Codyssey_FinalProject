-- 기존 002의 AI 로그 정의만 분리 적용한다.
-- 기존 학습 테이블은 변경하지 않는다.
-- 이미 ai_call_logs가 있다면 재실행하지 말고 구조를 확인한다.

begin;

create table public.ai_call_logs (
    id bigint generated always as identity primary key,
    user_id uuid references auth.users(id) on delete set null,
    feature text not null,
    model text,
    source text,
    tool_calls int not null default 0,
    latency_ms int,
    message text,
    created_at timestamptz not null default now()
);

create index ai_call_logs_feature_created_idx
    on public.ai_call_logs (feature, created_at desc);

create index ai_call_logs_created_idx
    on public.ai_call_logs (created_at desc);

create index ai_call_logs_user_idx
    on public.ai_call_logs (user_id);

alter table public.ai_call_logs enable row level security;

revoke all privileges on table public.ai_call_logs
    from public, anon, authenticated;

revoke all privileges on sequence public.ai_call_logs_id_seq
    from public, anon, authenticated;

grant select, insert, update, delete
    on table public.ai_call_logs to service_role;

grant usage, select
    on sequence public.ai_call_logs_id_seq to service_role;

commit;
