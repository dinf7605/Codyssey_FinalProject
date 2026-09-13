import BlockCard from '@/components/BlockCard';
import SectionTitle from '@/components/SectionTitle';
import { todayBlocks, goal } from '@/lib/mock';
import { dday } from '@/lib/ui';

// FR-PLAN-04 일정 조회(주간) / FR-PLAN-05 블록 수동 편집
// FR-PLAN-07 야간 재조정 변경 내역 / FR-PACE-01 중간 목표

const DAYS = ['월', '화', '수', '목', '금', '토', '일'];
const WEEK = [
  { d: 8, dots: ['done', 'done'] },
  { d: 9, dots: ['done'] },
  { d: 10, dots: ['done', 'miss'] },
  { d: 11, dots: ['done', 'done', 'done'] },
  { d: 12, dots: ['done'] },
  { d: 13, dots: [] },
  { d: 14, dots: ['plan', 'plan', 'plan'], today: true },
];

const CHANGES = [
  { type: '이동', what: '데이터베이스 구축 3단원', reason: '어제 미완료분을 오늘로 당겼습니다' },
  { type: '추가', what: '기출 풀이 60분', reason: '남은 기간에 맞춰 복습 블록을 넣었습니다' },
];

export default function SchedulePage() {
  return (
    <>
      <header className="stack" style={{ gap: 4 }}>
        <h1 style={{ fontSize: 20 }}>일정</h1>
        <p className="muted tiny">{goal.title} · {dday(goal.dDay)}</p>
      </header>

      <section>
        <SectionTitle>이번 주</SectionTitle>
        <div className="week">
          {WEEK.map((day, i) => (
            <div key={day.d} className={day.today ? 'day day-today' : 'day'}>
              <span className="day-name">{DAYS[i]}</span>
              <span className="day-num">{day.d}</span>
              <div style={{ display: 'flex', gap: 3, marginTop: 2 }}>
                {day.dots.map((kind, j) => (
                  <span
                    key={j}
                    className={kind === 'done' ? 'dot dot-done' : kind === 'miss' ? 'dot dot-miss' : 'dot'}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
        <p className="hint" style={{ marginTop: 'var(--gap-2)' }}>
          완료 · 미완료 · 예정을 색과 위치로 구분합니다
        </p>
      </section>

      <section>
        <SectionTitle>오늘 배치된 블록</SectionTitle>
        <ul className="list">
          {todayBlocks.map((block) => (
            <BlockCard key={block.id} block={block} />
          ))}
        </ul>
        <p className="hint" style={{ marginTop: 'var(--gap-2)' }}>
          길게 눌러 옮기면 선행 관계 위반 여부를 즉시 확인합니다
        </p>
      </section>

      <section>
        <SectionTitle>어젯밤 바뀐 내용</SectionTitle>
        <div className="card rows">
          {CHANGES.map((c) => (
            <div className="row" key={c.what}>
              <div className="row-main">
                <b>{c.what}</b>
                <span>{c.reason}</span>
              </div>
              <span className="badge">{c.type}</span>
            </div>
          ))}
        </div>
        <p className="hint" style={{ marginTop: 'var(--gap-2)' }}>
          매일 새벽 3시에 미완료 블록을 남은 기간에 다시 배치합니다 · 되돌리기 1회 가능
        </p>
      </section>
    </>
  );
}
