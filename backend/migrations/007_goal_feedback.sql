-- 007 — 추천 피드백 저장 (FR-GOAL-08, 담당 B)
--
-- 지금까지는 POST /goal/feedback 이 받기만 하고 저장하지 않았다.
-- 비회원도 쓰는 화면이라 user_id 는 필수로 두지 않는다 — 익명 세션(session_id)은
-- 항상 있고, 로그인된 사용자면 user_id 도 같이 남긴다 (000/004 의 DB 기준과 동일하게
-- auth.users(id) 를 가리키는 컬럼명은 user_id 로 통일).

create table if not exists public.goal_feedback (
    id           bigint generated always as identity primary key,
    session_id   text not null,
    user_id      uuid references auth.users(id) on delete cascade,
    goal_id      text not null,
    interested   boolean not null,
    reason       text,
    created_at   timestamptz not null default now()
);

create index if not exists goal_feedback_session_idx
    on public.goal_feedback (session_id, created_at desc);

create index if not exists goal_feedback_user_idx
    on public.goal_feedback (user_id, created_at desc);

alter table public.goal_feedback enable row level security;

-- 백엔드는 서비스 키로 쓰기 때문에 이 정책과 무관하게 insert 된다.
-- 브라우저가 공개 키로 직접 읽으려는 경우만 본인 것으로 제한한다.
create policy "users can read own goal feedback"
    on public.goal_feedback for select
    using (auth.uid() = user_id);
