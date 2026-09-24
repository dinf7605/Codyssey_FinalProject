-- 004 — DB 기준 통일 (backend/README.md "DB 기준" 참고)
--
--   1. 사용자를 가리키는 컬럼은 전부 user_id uuid → auth.users(id)
--      000 의 users · notification_logs 만 auth_id 를 쓰고 있었다
--   2. 비밀번호는 DB 에 저장하지 않는다 — Supabase Auth 가 해싱·저장한다 (기능명세서 K15)
--
-- 적용 시점 데이터 0건이라 이름 변경의 부담이 가장 적었다.
-- RLS 정책은 컬럼 이름 변경을 자동으로 따라간다.

alter table public.users rename column auth_id to user_id;
alter table public.users drop column if exists password_hash;

alter table public.notification_logs rename column auth_id to user_id;
alter index if exists public.notification_logs_auth_sent_idx
    rename to notification_logs_user_sent_idx;
