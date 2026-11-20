-- 전시 부스 시연 계정 20개 (test01@test01.com ~ test20@test20.com)
--
-- Supabase 대시보드 › SQL Editor 에 통째로 붙여 넣고 한 번 실행한다. 다시 실행해도 된다 (지우고 새로 만든다).
-- 비밀번호는 각 계정의 이메일과 같다.
--
-- 하는 일
--   ① 기존 test 계정을 지운다 — test@test.com, test01~05@test.com, 그리고 전에 만든 시연 계정
--      계정을 지우면 그 계정의 계획 · 학습 기록 · 알림도 함께 지워진다 (외래키 cascade)
--   ② 탈퇴 보관 트리거가 방금 옮겨 놓은 test 프로필 보관본을 지운다 (시연 계정은 1년 보관할 이유가 없다)
--   ③ 시연 계정 20개를 만든다 — 메일 인증 완료 상태 · 필수 동의 2개 완료 · 닉네임 시연01~시연20
--
-- 주의
--   - POP 에 공개하는 계정이다. 관리자 권한을 주지 않는다.
--   - 누구나 로그인할 수 있으므로 방문객이 비밀번호를 바꾸거나 탈퇴할 수 있다. 그러면 이 SQL 을 다시 실행한다.
--   - 행사가 끝나면 맨 아래 '정리' 를 실행해 지운다.

begin;

-- ① 기존 test 계정 삭제
delete from auth.users
where email ~ '^test[0-9]*@test[0-9]*\.com$';

-- ② 방금 생긴 보관본 삭제
delete from private.withdrawn_profiles
where email ~ '^test[0-9]*@test[0-9]*\.com$';

-- ③ 시연 계정 20개
with numbered as (
    select n,
           gen_random_uuid() as id,
           'test' || lpad(n::text, 2, '0') || '@test' || lpad(n::text, 2, '0') || '.com' as email
    from generate_series(1, 20) as n
),
new_auth as (
    insert into auth.users (
        instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
        raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
        confirmation_token, recovery_token, email_change, email_change_token_new
    )
    select '00000000-0000-0000-0000-000000000000', id, 'authenticated', 'authenticated', email,
           extensions.crypt(email, extensions.gen_salt('bf')),   -- 비밀번호 = 이메일
           now(),
           '{"provider": "email", "providers": ["email"]}'::jsonb, '{}'::jsonb, now(), now(),
           '', '', '', ''
    from numbered
    returning id, email
),
new_identity as (
    insert into auth.identities (
        id, user_id, provider_id, provider, identity_data, last_sign_in_at, created_at, updated_at
    )
    select gen_random_uuid(), id, id::text, 'email',
           jsonb_build_object('sub', id::text, 'email', email, 'email_verified', true, 'phone_verified', false),
           now(), now(), now()
    from new_auth
    returning user_id
)
insert into public.users (
    user_id, email, nickname, agree_privacy, agree_ai_notice, agree_marketing, ai_notice_version, agreed_at
)
select a.id, a.email, '시연' || substring(a.email from 5 for 2), true, true, false, 'v1', now()
from new_auth a
join new_identity i on i.user_id = a.id;

commit;

-- 확인 — 20줄이 나오고 confirmed · profile 이 모두 true 여야 한다
select u.email,
       u.email_confirmed_at is not null as confirmed,
       exists (select 1 from public.users p where p.user_id = u.id) as profile
from auth.users u
where u.email ~ '^test[0-9]{2}@test[0-9]{2}\.com$'
order by u.email;


-- ── 정리 (행사가 끝난 뒤 따로 실행) ────────────────────────────────────
-- begin;
-- delete from auth.users where email ~ '^test[0-9]{2}@test[0-9]{2}\.com$';
-- delete from private.withdrawn_profiles where email ~ '^test[0-9]{2}@test[0-9]{2}\.com$';
-- commit;
