-- 008 — 야간 재조정 · 변경 내역 · 블록 수동 편집 · 완료 취소 (담당 C)
--
--   FR-PLAN-06  매일 03:00 미완료 블록을 남은 기간에 다시 놓는다. 되돌리기 1회, 3일 연속이면 기한 조정 제안
--   FR-PLAN-07  어젯밤 무엇이 바뀌었는지 (추가·이동·삭제, 7일 보관)
--   FR-PLAN-05  블록을 직접 옮기거나 지운다 — 옮긴 블록은 재조정에서 고정(locked)
--   FR-STUDY-02 완료 취소는 24시간 이내만 → 완료 시각이 필요하다
--
-- 005~007(담당 E·B)과 겹치는 테이블이 없어 순서와 상관없이 적용된다.

-- 재조정은 사용자의 빈 시간표가 있어야 다시 놓을 수 있다 (schemas.plan.Availability 모양 그대로)
alter table public.study_plans add column if not exists availability jsonb;

alter table public.plan_blocks add column if not exists done_at timestamptz;

-- ── 재조정 한 번 = 한 묶음. 되돌리기 단위 ─────────────────
create table if not exists public.plan_reschedule_runs (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users(id) on delete cascade,
    plan_id         uuid not null references public.study_plans(id) on delete cascade,
    summary         text not null,                       -- 화면 맨 위 한 줄 (AI 요약 또는 규칙 문구)
    summary_source  text not null check (summary_source in ('ai', 'template')),
    moved           int  not null default 0,
    unplaced        int  not null default 0,
    undone_at       timestamptz,                         -- 되돌렸으면 시각. 한 번만 된다
    created_at      timestamptz not null default now()
);

create index if not exists plan_reschedule_runs_user_created_idx
    on public.plan_reschedule_runs (user_id, created_at desc);
create index if not exists plan_reschedule_runs_plan_idx
    on public.plan_reschedule_runs (plan_id);

-- ── 블록 하나가 어떻게 바뀌었는지 ─────────────────────────
create table if not exists public.plan_changes (
    id            bigint generated always as identity primary key,
    user_id       uuid not null references auth.users(id) on delete cascade,
    plan_id       uuid not null references public.study_plans(id) on delete cascade,
    run_id        uuid references public.plan_reschedule_runs(id) on delete cascade,  -- 수동 편집은 null
    block_id      uuid references public.plan_blocks(id) on delete set null,
    origin        text not null check (origin in ('nightly', 'manual')),
    change_type   text not null check (change_type in ('add', 'move', 'delete', 'unplaced')),
    title         text not null,                         -- 블록을 지워도 무엇이었는지 남도록
    before_start  timestamptz,
    before_end    timestamptz,
    after_start   timestamptz,
    after_end     timestamptz,
    reason        text not null,
    created_at    timestamptz not null default now()
);

create index if not exists plan_changes_user_created_idx
    on public.plan_changes (user_id, created_at desc);
create index if not exists plan_changes_plan_idx on public.plan_changes (plan_id);
create index if not exists plan_changes_run_idx on public.plan_changes (run_id);
create index if not exists plan_changes_block_idx on public.plan_changes (block_id);

-- ── RLS: 본인 것만 읽는다. 쓰기는 백엔드만 ───────────────
alter table public.plan_reschedule_runs enable row level security;
alter table public.plan_changes         enable row level security;

create policy "users can read own reschedule runs"
    on public.plan_reschedule_runs for select
    using ((select auth.uid()) = user_id);

create policy "users can read own plan changes"
    on public.plan_changes for select
    using ((select auth.uid()) = user_id);
