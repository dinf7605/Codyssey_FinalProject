-- 학습 단위(주제) 최대 600분 — 단위와 블록 분리 (10-02 결정)
--
-- 예전엔 단위 = 블록(최대 120분)이라 단위 25개 × 120분 = 계획 전체 50시간이 상한이었다.
-- 이제 단위는 30~600분이고, 배치할 때 120분 이하 블록 여러 개로 나눠 놓는다
-- (backend/schemas/plan.py MAX_UNIT_MINUTES · MAX_BLOCK_MINUTES, services/scheduler.py).
-- 블록(plan_blocks.minutes)은 원래 '0보다 큼'만 검사하므로 바꿀 것이 없다.
--
-- 이 마이그레이션을 적용하기 전에는 120분이 넘는 단위가 든 계획을 저장할 때
-- study_units_estimated_minutes_check 위반으로 저장이 실패한다.

alter table public.study_units
    drop constraint if exists study_units_estimated_minutes_check;

alter table public.study_units
    add constraint study_units_estimated_minutes_check
    check (estimated_minutes between 30 and 600);
