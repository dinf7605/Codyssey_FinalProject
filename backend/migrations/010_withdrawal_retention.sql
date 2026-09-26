-- 적용 대상: 2026-09-26 확인한 auth_id 기반 운영 스키마.
-- 프로필만 1년 보관. Auth 관리자 삭제도 동일한 보관 정책 적용.
-- Supabase에서 pg_cron 확장을 먼저 활성화해야 한다.
begin;

-- 필요한 컬럼/타입과 삭제 연결을 확인하고 불일치하면 전체 적용 중단.
do $$
begin
    if not exists (select 1 from information_schema.columns where table_schema='public' and table_name='users' and column_name='auth_id' and data_type='uuid')
       or not exists (select 1 from information_schema.columns where table_schema='public' and table_name='study_plans' and column_name='auth_id' and data_type='uuid')
       or not exists (select 1 from information_schema.columns where table_schema='public' and table_name='study_plans' and column_name='user_id' and data_type='bigint') then
        raise exception 'Expected auth_id/bigint schema is missing; do not apply to the renamed UUID user_id schema';
    end if;
    if not exists (select 1 from pg_constraint where conrelid='public.plan_blocks'::regclass and confrelid='public.study_plans'::regclass and contype='f' and confdeltype='c')
       or not exists (select 1 from pg_constraint where conrelid='public.notification_logs'::regclass and confrelid='public.plan_blocks'::regclass and contype='f' and confdeltype='c') then
        raise exception 'Required plan/block/notification cascade constraints are missing';
    end if;
end;
$$;
create unique index if not exists users_auth_id_retention_unique on public.users(auth_id);

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table private.withdrawn_profiles (
    archive_id bigint generated always as identity primary key,
    email text,
    nickname text,
    agree_privacy boolean,
    agree_ai_notice boolean,
    agree_marketing boolean,
    agreed_at timestamptz,
    withdrawn_at timestamptz not null,
    expires_at timestamptz not null,
    check (expires_at > withdrawn_at)
);
alter table private.withdrawn_profiles enable row level security;
revoke all on private.withdrawn_profiles from public, anon, authenticated, service_role;
create index withdrawn_profiles_expiry_idx on private.withdrawn_profiles(expires_at);

-- 인증 ID나 비밀번호/토큰, 학습 데이터를 보관본에 넣지 않는다.
create function private.archive_withdrawn_profile()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
    profile record;
    target record;
    deleted_at timestamptz := clock_timestamp();
    profile_id bigint;
begin
    select * into profile from public.users where auth_id = old.id for update;
    if found then
        profile_id := profile.id;
        insert into private.withdrawn_profiles (
            email, nickname, agree_privacy, agree_ai_notice, agree_marketing,
            agreed_at, withdrawn_at, expires_at
        ) values (
            profile.email, profile.nickname, profile.agree_privacy,
            profile.agree_ai_notice, profile.agree_marketing, profile.agreed_at,
            deleted_at, (deleted_at at time zone 'UTC' + interval '1 year') at time zone 'UTC'
        );
    end if;

    -- 스키마가 다른 두 버전에 대응. 인증 ID인 UUID 컬럼만 비교한다.
    -- 명시한 서비스 테이블에 한정하며 공용 공모전/커리큘럼은 보존한다.
    for target in
        select c.table_name, c.column_name
        from information_schema.columns c
        where c.table_schema = 'public'
          and c.data_type = 'uuid'
          and c.column_name in ('auth_id', 'user_id')
          and c.table_name in (
              'notification_logs', 'user_notification_settings', 'study_sessions',
              'user_memories', 'contest_feedback', 'contest_recommendations',
              'goal_feedback', 'ai_call_logs', 'plan_changes',
              'plan_reschedule_runs'
          )
    loop
        execute format('delete from public.%I where %I = $1', target.table_name, target.column_name)
        using old.id;
    end loop;

    -- 운영 스키마의 숫자형 user_id와 UUID auth_id 모두 반영한다.
    -- plan_blocks와 notification_logs의 연결된 행은 기존 FK cascade로 삭제된다.
    delete from public.study_plans
      where auth_id = old.id or user_id = profile_id;
    delete from public.users where auth_id = old.id;
    return old;
end;
$$;
revoke all on function private.archive_withdrawn_profile() from public, anon, authenticated, service_role;

create trigger archive_profile_before_auth_delete
before delete on auth.users
for each row execute function private.archive_withdrawn_profile();

create function private.purge_expired_profiles()
returns bigint language plpgsql security definer set search_path = '' as $$
declare affected bigint;
begin
    delete from private.withdrawn_profiles where expires_at <= clock_timestamp();
    get diagnostics affected = row_count;
    return affected;
end;
$$;
revoke all on function private.purge_expired_profiles() from public, anon, authenticated, service_role;

-- 매시간 실행: 삭제 예정 시각 이후 첫 실행에서 삭제 (최대 약 1시간 지연).
select cron.schedule(
    'purge-withdrawn-profiles', '0 * * * *',
    'select private.purge_expired_profiles();'
);

-- 서비스 키만 확인 가능. 설치/스케줄이 없으면 백엔드가 탈퇴를 중단한다.
create function public.withdrawal_retention_ready()
returns boolean language sql security definer set search_path = '' as $$
    select exists (
        select 1 from pg_catalog.pg_trigger
        where tgrelid = 'auth.users'::regclass
          and tgname = 'archive_profile_before_auth_delete'
          and tgfoid = 'private.archive_withdrawn_profile()'::regprocedure
          and tgenabled in ('O', 'A')
    ) and exists (
        select 1 from cron.job
        where jobname = 'purge-withdrawn-profiles' and active
          and schedule = '0 * * * *'
          and command = 'select private.purge_expired_profiles();'
    );
$$;
revoke all on function public.withdrawal_retention_ready() from public, anon, authenticated;
grant execute on function public.withdrawal_retention_ready() to service_role;

commit;
