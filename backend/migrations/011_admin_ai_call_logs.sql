-- 011 — 관리자 AI 처리 기록 조회용 정리 (담당 E, FR-ADMIN-02)
--
-- ai_call_logs 테이블은 002 에서 이미 만들었다 (담당 C 가 학습 분해 때 기록). 여기서는 다시 만들지 않고
-- 관리자 화면(/admin/ai-logs)의 날짜별 조회에 필요한 것만 더한다. 2026-09-27 다시 씀 —
-- 처음 판은 create table 을 다시 해서 공용 DB 에 적용하면 오류가 났다.

-- 날짜 범위로 최신순 조회 (routers/admin.py list_ai_logs)
create index if not exists ai_call_logs_created_idx
    on public.ai_call_logs (created_at desc);

-- 브라우저 키로는 아예 접근하지 못하게 한다 (RLS 정책도 없다). 읽기·쓰기는 백엔드 서비스 키만
revoke all privileges on table public.ai_call_logs from public, anon, authenticated;
revoke all privileges on sequence public.ai_call_logs_id_seq from public, anon, authenticated;
grant select, insert, update, delete on table public.ai_call_logs to service_role;
grant usage, select on sequence public.ai_call_logs_id_seq to service_role;
