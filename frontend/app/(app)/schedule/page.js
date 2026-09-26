import PlanBuilder from '@/components/PlanBuilder';
import PlanCalendar from '@/components/PlanCalendar';
import PlanChanges from '@/components/PlanChanges';
import SectionTitle from '@/components/SectionTitle';

// 일정 화면 — 전부 실제 API (담당 C)
//   FR-PLAN-04 일정 조회(주·월) · FR-PLAN-05 블록 옮기기·지우기 · FR-PLAN-06 지금 다시 놓기
//   FR-PLAN-07 최근 바뀐 일정 (변경이 없으면 영역을 숨긴다) · 되돌리기 1회
//   FR-PLAN-02·03 계획 만들기 → 공부량 점검 → 확정

export default function SchedulePage() {
  return (
    <>
      <header className="stack" style={{ gap: 6 }}>
        <h1 className="title">일정</h1>
      </header>

      <section className="sec">
        <SectionTitle>내 학습 일정</SectionTitle>
        <PlanCalendar />
      </section>

      <PlanChanges />

      <section className="sec" id="plan-builder">
        <SectionTitle>학습 계획 만들기</SectionTitle>
        <PlanBuilder />
      </section>
    </>
  );
}
