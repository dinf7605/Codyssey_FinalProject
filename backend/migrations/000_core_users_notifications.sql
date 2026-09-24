-- 000 — 회원·알림 (담당 E 코드가 쓰는 테이블)
--
-- 지금까지 대시보드에서 손으로 만들어 쓰던 테이블을 SQL 로 옮겼다.
-- 새 Supabase 프로젝트에서도 같은 구조가 나오게 하려는 것이다.
-- 컬럼은 routers/auth.py · settings.py · notifications.py 가 실제로 읽고 쓰는 것만 넣었다.
--
-- 백엔드는 Service Role(secret) 키로 접속하므로 RLS 를 통과한다.
-- RLS 는 브라우저에서 공개 키로 직접 읽을 때를 막기 위한 것이다.

-- ── 회원 프로필 (FR-AUTH-*, FR-MY-*) ─────────────────────
create table if not exists public.users (
    id               bigint generated always as identity primary key,
    auth_id          uuid not null unique references auth.users(id) on delete cascade,
    email            text not null,
    nickname         text not null,
    -- 로그인은 Supabase Auth 가 처리한다. 이 컬럼은 routers/auth.py 가 아직 쓰고 있어 남겨 둔다.
    -- 기능명세서(K15)는 "비밀번호 해싱·저장은 Supabase Auth 가 처리" — 정리 대상 (담당 E 확인 중)
    password_hash    text,
    agree_privacy    boolean not null default false,
    agree_ai_notice  boolean not null default false,
    agree_marketing  boolean not null default false,
    agreed_at        timestamptz,
    created_at       timestamptz not null default now()
);

alter table public.users enable row level security;

create policy "users can read own profile"
    on public.users for select
    using (auth.uid() = auth_id);

-- ── 알림 기록 (FR-ALARM-*) ──────────────────────────────
create table if not exists public.notification_logs (
    id        bigint generated always as identity primary key,
    auth_id   uuid not null references auth.users(id) on delete cascade,
    type      text not null,
    message   text not null,
    is_read   boolean not null default false,
    sent_at   timestamptz not null default now()
);

create index if not exists notification_logs_auth_sent_idx
    on public.notification_logs (auth_id, sent_at desc);

alter table public.notification_logs enable row level security;

create policy "users can read own notifications"
    on public.notification_logs for select
    using (auth.uid() = auth_id);
