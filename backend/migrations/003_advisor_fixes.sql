-- 003 — Supabase 점검 도구(Advisors) 경고 정리
--
-- 000~002 를 적용한 뒤 나온 WARN 을 고친다. 이미 적용한 파일은 고치지 않고 여기서 덮어쓴다.
--
--   function_search_path_mutable  set_updated_at 에 search_path 고정
--   extension_in_public           vector 확장을 extensions 스키마로 이동
--   auth_rls_initplan             정책의 auth.uid() 를 (select auth.uid()) 로 — 행마다 다시 계산하지 않게
--   unindexed_foreign_keys        외래키 4개에 인덱스
--
-- 남겨 둔 INFO
--   rls_enabled_no_policy  ai_call_logs · batch_runs · contest_embeddings 는
--                          일부러 정책이 없다 = 공개 키로는 못 읽고 백엔드(Service Role)만 접근
--   unused_index           막 만든 DB 라 아직 쓰인 적이 없을 뿐이다

-- ── 보안 ──────────────────────────────────────────────
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

alter extension vector set schema extensions;

-- ── RLS 정책: auth.uid() 를 한 번만 계산 ─────────────────
alter policy "users can read own profile" on public.users
    using ((select auth.uid()) = auth_id);

alter policy "users can read own notifications" on public.notification_logs
    using ((select auth.uid()) = auth_id);

alter policy "users can read own recommendations" on public.contest_recommendations
    using ((select auth.uid()) = user_id);

alter policy "users can read own feedback" on public.contest_feedback
    using ((select auth.uid()) = user_id);

alter policy "users can insert own feedback" on public.contest_feedback
    with check ((select auth.uid()) = user_id);

alter policy "users can update own feedback" on public.contest_feedback
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

alter policy "users can delete own feedback" on public.contest_feedback
    using ((select auth.uid()) = user_id);

alter policy "users can read own memories" on public.user_memories
    using ((select auth.uid()) = user_id);

alter policy "users can delete own memories" on public.user_memories
    using ((select auth.uid()) = user_id);

alter policy "users can read own plans" on public.study_plans
    using ((select auth.uid()) = user_id);

alter policy "users can read own units" on public.study_units
    using (exists (select 1 from public.study_plans p
                   where p.id = plan_id and p.user_id = (select auth.uid())));

alter policy "users can read own blocks" on public.plan_blocks
    using (exists (select 1 from public.study_plans p
                   where p.id = plan_id and p.user_id = (select auth.uid())));

alter policy "users can read own sessions" on public.study_sessions
    using ((select auth.uid()) = user_id);

-- ── 외래키 인덱스 ─────────────────────────────────────
create index if not exists ai_call_logs_user_idx
    on public.ai_call_logs (user_id);
create index if not exists contest_feedback_contest_idx
    on public.contest_feedback (contest_id);
create index if not exists contest_recommendations_contest_idx
    on public.contest_recommendations (contest_id);
create index if not exists study_sessions_block_idx
    on public.study_sessions (block_id);
