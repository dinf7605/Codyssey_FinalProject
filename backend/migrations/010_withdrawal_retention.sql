-- 010 — 탈퇴 프로필 1년 분리 보관 (담당 E, FR-MY-04)
--
-- 공용 DB(studypace, 004 이후 user_id uuid 스키마)용. 2026-09-27 다시 씀.
-- 처음 판은 auth_id·bigint user_id 스키마(다른 Supabase 프로젝트)용이라 공용 DB 에는 적용되지 않았다 — git 기록에 남아 있다.
--
-- 탈퇴 = auth.users 행 삭제 (백엔드 /settings/withdraw 가 auth.admin.delete_user 를 부른다)
--   ① 이 트리거가 삭제 직전에 public.users 프로필을 private.withdrawn_profiles 로 옮긴다
--      인증 ID·비밀번호·토큰·학습 데이터는 보관본에 넣지 않는다
--   ② 서비스 데이터는 외래키가 지운다 — 사용자 테이블은 모두 user_id → auth.users on delete cascade (DB 기준)
--      ai_call_logs 만 on delete set null 이라 여기서 따로 지운다
--   ③ pg_cron 이 매시간 1년 지난 보관본을 지운다 (최대 약 1시간 지연)
-- 대시보드에서 관리자가 계정을 지워도 같은 규칙이 적용된다.

create extension if not exists pg_cron with schema pg_catalog;
grant usage on schema cron to postgres;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table if not exists private.withdrawn_profiles (
    archive_id       bigint generated always as identity primary key,
    email            text,
    nickname         text,
    agree_privacy    boolean,
    agree_ai_notice  boolean,
    agree_marketing  boolean,
    agreed_at        timestamptz,
    withdrawn_at     timestamptz not null,
    expires_at       timestamptz not null,
    check (expires_at > withdrawn_at)
);
alter table private.withdrawn_profiles enable row level security;
revoke all on private.withdrawn_profiles from public, anon, authenticated, service_role;
create index if not exists withdrawn_profiles_expiry_idx on private.withdrawn_profiles (expires_at);

create or replace function private.archive_withdrawn_profile()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
    profile   record;
    removed   timestamptz := clock_timestamp();
begin
    select * into profile from public.users where user_id = old.id;
    if found then
        insert into private.withdrawn_profiles (
            email, nickname, agree_privacy, agree_ai_notice, agree_marketing,
            agreed_at, withdrawn_at, expires_at
        ) values (
            profile.email, profile.nickname, profile.agree_privacy,
            profile.agree_ai_notice, profile.agree_marketing, profile.agreed_at,
            removed, (removed at time zone 'UTC' + interval '1 year') at time zone 'UTC'  -- 세션 시간대와 상관없이 UTC 기준 1년
        );
    end if;

    delete from public.ai_call_logs where user_id = old.id;
    return old;  -- 나머지(users, 계획·학습·알림·공모전·메모리)는 외래키 cascade
end;
$$;
revoke all on function private.archive_withdrawn_profile() from public, anon, authenticated, service_role;

drop trigger if exists archive_profile_before_auth_delete on auth.users;
create trigger archive_profile_before_auth_delete
before delete on auth.users
for each row execute function private.archive_withdrawn_profile();

create or replace function private.purge_expired_profiles()
returns bigint language plpgsql security definer set search_path = '' as $$
declare affected bigint;
begin
    delete from private.withdrawn_profiles where expires_at <= clock_timestamp();
    get diagnostics affected = row_count;
    return affected;
end;
$$;
revoke all on function private.purge_expired_profiles() from public, anon, authenticated, service_role;

-- 같은 이름이면 덮어쓴다 — 다시 적용해도 중복 등록되지 않는다
select cron.schedule('purge-withdrawn-profiles', '0 * * * *', 'select private.purge_expired_profiles();');

-- 서비스 키만 부를 수 있다. 트리거나 스케줄이 없으면 백엔드가 탈퇴를 멈춘다 (계정만 지워지고 보관이 안 되는 일을 막음)
create or replace function public.withdrawal_retention_ready()
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
