-- 018 — 알림 세부 규칙 · 관심 공모전 준비 블록 · AI 고지 재동의 (FR-MY-03 · FR-MY-05 · FR-CONT-07 · FR-JOIN-03)
--
-- 모두 더하기만 한다 (기존 행·열을 지우거나 바꾸지 않는다).

-- ── FR-MY-03 알림 3종을 각각 설정 ────────────────────────
-- null = 아직 고른 적 없음 → 가입 때 '학습 알림 수신(선택)' 동의(users.agree_marketing)를 따른다
alter table public.user_notification_settings
    add column if not exists notify_replan   boolean,   -- 재조정 결과 (야간 재조정이 블록을 옮겼을 때)
    add column if not exists notify_deadline boolean,   -- 마감 임박 (관심 공모전 마감 24시간 전 · 알림 전체 끄기와 별개)
    add column if not exists notify_nudge    boolean;   -- 학습 독촉 (미완료 · 하루 마감 — 강도 '강'에서)

-- ── 공모전 알림 중복 방지 ─────────────────────────────────
alter table public.notification_logs
    add column if not exists contest_id uuid references public.contests(id) on delete cascade;

create unique index if not exists notification_logs_user_contest_type_unique
    on public.notification_logs (user_id, contest_id, type)
    where contest_id is not null;

create index if not exists notification_logs_contest_idx
    on public.notification_logs (contest_id)
    where contest_id is not null;

-- ── FR-CONT-07 관심 공모전 → 마감 D-7 · D-3 준비 블록 ─────
-- 준비 블록은 진행 중인 목표(plan_id)에 학습 단위로 더한다. unit_keys 로 관심 해제 때 함께 지운다.
create table if not exists public.contest_interests (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users(id) on delete cascade,
    contest_id  uuid not null references public.contests(id) on delete cascade,
    plan_id     uuid references public.study_plans(id) on delete set null,
    unit_keys   text[] not null default '{}',
    created_at  timestamptz not null default now(),
    unique (user_id, contest_id)
);

create index if not exists contest_interests_contest_idx on public.contest_interests (contest_id);
create index if not exists contest_interests_plan_idx on public.contest_interests (plan_id);

alter table public.contest_interests enable row level security;

drop policy if exists "users can read own contest interests" on public.contest_interests;
create policy "users can read own contest interests"
    on public.contest_interests for select
    using ((select auth.uid()) = user_id);

-- ── FR-JOIN-03 AI 이용 고지 문구 버전 ─────────────────────
-- 문구가 바뀌면 백엔드 AI_NOTICE_VERSION 을 올린다 → 다음 로그인에서 다시 동의를 받는다
alter table public.users
    add column if not exists ai_notice_version text;

-- 이미 동의한 사람은 지금 문구(v1)에 동의한 것이다
update public.users set ai_notice_version = 'v1'
where agree_ai_notice and ai_notice_version is null;
