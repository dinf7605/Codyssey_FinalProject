-- 014 — 알림 설정 · 알림 중복 방지 (담당 E, FR-ALARM-01 · FR-MY-05) — 005·006 을 공용 DB 기준으로 다시 쓴 것
--
-- 005·006 은 개인 DB(auth_id · bigint id) 기준이라 공용 DB 에 적용할 수 없었다.
--   - notification_logs.block_id 를 bigint 로 만들어 plan_blocks.id(uuid)를 가리킴 → 적용 시 오류
--   - 006 이 이미 있는 study_plans · plan_blocks 를 다른 모양으로 다시 정의
--   - user_notification_settings 를 auth_id 로 만들었는데 스케줄러 코드는 user_id 로 조회
-- 그래서 두 파일은 지우고, 코드(services/notification_scheduler.py)가 실제로 쓰는 것만 여기 만든다.

-- ── 블록별 알림 기록 · 같은 알림 두 번 방지 ─────────────────
-- 블록을 지우면 그 블록의 알림 기록도 지운다 (005 의 의도 그대로)
alter table public.notification_logs
    add column if not exists block_id uuid references public.plan_blocks(id) on delete cascade;

-- 스케줄러가 1분마다 돌아도 같은 블록 · 같은 종류 알림은 한 번만 남는다
create unique index if not exists notification_logs_user_block_type_unique
    on public.notification_logs (user_id, block_id, type)
    where block_id is not null;

-- block_id 외래키용 인덱스는 위 unique 인덱스가 맡지 못한다 (첫 열이 user_id) — 블록 삭제 cascade 용
create index if not exists notification_logs_block_idx
    on public.notification_logs (block_id)
    where block_id is not null;

-- ── 사용자 알림 설정 (한 사람당 한 줄) ──────────────────────
-- 행이 없으면 기본값(알림 켬 · 방해금지 없음)으로 본다 — 스케줄러가 그렇게 처리한다
create table if not exists public.user_notification_settings (
    user_id                  uuid primary key references auth.users(id) on delete cascade,
    enabled                  boolean not null default true,
    reminder_minutes_before  integer not null default 10 check (reminder_minutes_before between 1 and 120),
    quiet_start              time,          -- 방해금지 시작 (한국 시각, 예: 22:00)
    quiet_end                time,          -- 방해금지 끝 (자정을 넘어도 된다, 예: 07:00)
    intensity                text not null default 'normal' check (intensity in ('low', 'normal', 'high')),
    created_at               timestamptz not null default now(),
    updated_at               timestamptz not null default now()
);

drop trigger if exists user_notification_settings_set_updated_at on public.user_notification_settings;
create trigger user_notification_settings_set_updated_at
    before update on public.user_notification_settings
    for each row execute function public.set_updated_at();

-- 본인 것만 읽는다. 쓰기는 백엔드(서비스 키)만
alter table public.user_notification_settings enable row level security;

drop policy if exists "users can read own notification settings" on public.user_notification_settings;
create policy "users can read own notification settings"
    on public.user_notification_settings for select
    using ((select auth.uid()) = user_id);
