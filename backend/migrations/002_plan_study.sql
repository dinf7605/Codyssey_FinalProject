-- 002 — 일정·학습 (담당 C: FR-PLAN-*, FR-STUDY-*, FR-ADMIN-02 근거)
--
-- 구조는 backend/schemas/plan.py 의 모델과 1:1 로 맞췄다.
--   study_plans     목표 하나에 대한 계획 (분해 결과가 어디서 왔는지 source 로 남긴다)
--   study_units     StudyUnit — 학습 단위. unit_key 는 에이전트가 붙인 u01, tpl-01 같은 ID
--   plan_blocks     Block — 달력에 놓인 블록
--   study_sessions  실제로 공부한 기록 (FR-STUDY-01/02). 5분 미만은 저장하지 않는다
--   ai_call_logs    AI 호출 기록 (FR-ADMIN-02 대시보드, AI 품질 평가 근거)

-- ── 계획 ──────────────────────────────────────────────
create table if not exists public.study_plans (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users(id) on delete cascade,
    goal_title  text not null,
    goal_id     text not null default 'custom',
    deadline    date not null,
    source      text not null check (source in ('agent', 'partial', 'template')),
    status      text not null default 'active' check (status in ('active', 'archived')),
    created_at  timestamptz not null default now()
);

create index if not exists study_plans_user_idx on public.study_plans (user_id, created_at desc);

-- ── 학습 단위 ─────────────────────────────────────────
create table if not exists public.study_units (
    id                 uuid primary key default gen_random_uuid(),
    plan_id            uuid not null references public.study_plans(id) on delete cascade,
    unit_key           text not null,
    title              text not null,
    estimated_minutes  int  not null check (estimated_minutes between 30 and 120),
    prerequisites      text[] not null default '{}',
    estimated          boolean not null default false,  -- 검색 자료 밖에서 AI 가 추정한 단위
    position           int not null default 0,
    unique (plan_id, unit_key)
);

-- ── 블록 ──────────────────────────────────────────────
create table if not exists public.plan_blocks (
    id          uuid primary key default gen_random_uuid(),
    plan_id     uuid not null references public.study_plans(id) on delete cascade,
    unit_key    text not null,
    title       text not null,
    start_at    timestamptz not null,
    end_at      timestamptz not null,
    minutes     int not null check (minutes > 0),
    locked      boolean not null default false,  -- 수동으로 옮긴 블록은 야간 재조정이 건드리지 않는다
    done        boolean not null default false,
    updated_at  timestamptz not null default now(),
    check (end_at > start_at)
);

create index if not exists plan_blocks_plan_start_idx on public.plan_blocks (plan_id, start_at);

-- ── 학습 기록 ─────────────────────────────────────────
create table if not exists public.study_sessions (
    id                bigint generated always as identity primary key,
    user_id           uuid not null references auth.users(id) on delete cascade,
    block_id          uuid references public.plan_blocks(id) on delete set null,
    started_at        timestamptz not null,
    ended_at          timestamptz not null,
    minutes           int not null check (minutes >= 5),
    expected_minutes  int,
    note              text,
    created_at        timestamptz not null default now(),
    check (ended_at > started_at)
);

create index if not exists study_sessions_user_started_idx
    on public.study_sessions (user_id, started_at desc);

-- ── AI 호출 기록 ───────────────────────────────────────
create table if not exists public.ai_call_logs (
    id          bigint generated always as identity primary key,
    user_id     uuid references auth.users(id) on delete set null,
    feature     text not null,            -- 예: 'plan.decompose'
    model       text,
    source      text,                     -- agent / partial / template
    tool_calls  int not null default 0,
    latency_ms  int,
    message     text,                     -- 폴백 사유 등
    created_at  timestamptz not null default now()
);

create index if not exists ai_call_logs_feature_created_idx
    on public.ai_call_logs (feature, created_at desc);

-- ── RLS: 본인 것만 읽는다. 쓰기는 백엔드(Service Role)만 ─────
alter table public.study_plans     enable row level security;
alter table public.study_units     enable row level security;
alter table public.plan_blocks     enable row level security;
alter table public.study_sessions  enable row level security;
alter table public.ai_call_logs    enable row level security;

create policy "users can read own plans"
    on public.study_plans for select
    using (auth.uid() = user_id);

create policy "users can read own units"
    on public.study_units for select
    using (exists (select 1 from public.study_plans p
                   where p.id = plan_id and p.user_id = auth.uid()));

create policy "users can read own blocks"
    on public.plan_blocks for select
    using (exists (select 1 from public.study_plans p
                   where p.id = plan_id and p.user_id = auth.uid()));

create policy "users can read own sessions"
    on public.study_sessions for select
    using (auth.uid() = user_id);

-- ai_call_logs 는 정책을 두지 않는다 = 공개 키로는 아무도 못 읽는다 (관리자 API 로만)
