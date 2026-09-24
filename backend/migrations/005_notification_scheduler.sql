-- 005 — 알림 스케줄러용 컬럼/설정 테이블

alter table public.notification_logs
add column if not exists block_id uuid references public.plan_blocks(id) on delete cascade;

create unique index if not exists notification_logs_user_block_type_unique
on public.notification_logs (user_id, block_id, type)
where block_id is not null;

create table if not exists public.user_notification_settings (
    user_id uuid primary key references auth.users(id) on delete cascade,
    enabled boolean not null default true,
    quiet_start time,
    quiet_end time,
    intensity text not null default 'normal'
        check (intensity in ('low', 'normal', 'high')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);