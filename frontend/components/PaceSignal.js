import { paceView, dday } from '@/lib/ui';

// FR-PACE-04 진도 신호등 + FR-MAIN-04 목표 진행률
// 색만으로 상태를 구분하지 않고 항상 문구를 함께 보여준다 (NFR-A11Y-01).

export default function PaceSignal({ goal, pace }) {
  const view = paceView(pace.state, Math.abs(pace.diffDays));
  const percent = Math.round((goal.unitsDone / goal.unitsTotal) * 100);

  return (
    <section className="sec">
      <div className="sec-head">
        <h2 className="h-sec">{goal.title}</h2>
        <span className="mono tiny dim">{dday(goal.dDay)}</span>
      </div>

      <div className="stack" style={{ gap: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span className="tiny muted">
            {goal.unitsDone} / {goal.unitsTotal} 단원
          </span>
          <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{percent}%</span>
        </div>

        <div
          className="bar"
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="목표 진행률"
        >
          <div className="bar-fill" style={{ width: percent + '%' }} />
        </div>

        <div style={{ display: 'flex', gap: 9, alignItems: 'baseline', marginTop: 4 }}>
          <span className={view.tone === 'muted' ? 'tag' : 'tag tag-' + view.tone}>{view.label}</span>
          <p className="tiny muted" style={{ flex: 1 }}>{pace.nextCheckpoint}</p>
        </div>
      </div>
    </section>
  );
}
