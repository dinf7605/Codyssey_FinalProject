import PlanBuilder from '@/components/PlanBuilder';
import PlanCalendar from '@/components/PlanCalendar';
import SectionTitle from '@/components/SectionTitle';

// FR-PLAN-02·03 계획 만들기 → 확정 / FR-PLAN-04 일정 조회(주·월) — 전부 실제 API (담당 C)
// FR-PLAN-05 블록 수동 편집 · FR-PLAN-07 재조정 내역은 API 가 생기면 붙인다.
// 변경 내역은 "변경이 없으면 영역을 숨김"(FR-PLAN-07)이라 지금은 그리지 않는다.

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

      <section className="sec">
        <SectionTitle>학습 계획 만들기</SectionTitle>
        <PlanBuilder />
      </section>
    </>
  );
}
