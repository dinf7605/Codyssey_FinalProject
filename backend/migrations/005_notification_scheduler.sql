-- 005 - 알림 스케줄러용 컬럼/설정 보강

alter table public.notification_logs
add column if not exists block_id bigint references public.plan_blocks(id) on delete cascade;

do $$
begin
  -- notification_logs가 auth_id를 쓰는 경우
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'notification_logs'
      and column_name = 'auth_id'
  ) and exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'notification_logs'
      and column_name = 'type'
  ) then
    execute '
      create unique index if not exists notification_logs_auth_block_type_unique
      on public.notification_logs (auth_id, block_id, type)
      where block_id is not null
    ';

  -- 혹시 user_id를 쓰는 구조인 경우
  elsif exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'notification_logs'
      and column_name = 'user_id'
  ) and exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'notification_logs'
      and column_name = 'type'
  ) then
    execute '
      create unique index if not exists notification_logs_user_block_type_unique
      on public.notification_logs (user_id, block_id, type)
      where block_id is not null
    ';

  else
    raise notice 'notification_logs에 auth_id/user_id 또는 type 컬럼이 없어 중복 방지 인덱스 생성을 건너뜁니다.';
  end if;
end $$;

alter table public.user_notification_settings
add column if not exists quiet_start time,
add column if not exists quiet_end time,
add column if not exists intensity text not null default 'normal';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'user_notification_settings_intensity_check'
  ) then
    alter table public.user_notification_settings
    add constraint user_notification_settings_intensity_check
    check (intensity in ('low', 'normal', 'high'));
  end if;
end $$;

alter table public.user_notification_settings enable row level security;