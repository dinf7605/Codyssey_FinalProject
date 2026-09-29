-- D 담당: 위비티 수집 범위를 제목·공고 링크·출처로 제한한다.
-- 마감일은 수집하지 않으므로 NULL 허용. 기존 상세 메타데이터는 이 변경에서 삭제하지 않는다.
alter table public.contests alter column deadline drop not null;

drop policy if exists "public can read active contests" on public.contests;
create policy "public can read active contests"
on public.contests for select
using (
  (status in ('upcoming', 'open') and deadline >= current_date)
  or (source = 'wevity' and status = 'unknown' and deadline is null)
);
