import { paceView, dday } from '@/lib/ui';

// FR-PACE-04 진도 신호등 + FR-MAIN-04 목표 진행률
// 색만으로 상태를 구분하지 않고 항상 문구를 함께 보여준다 (NFR-A11Y-01).

export default function PaceSignal({ goal, pace }) {
  const view = paceView(pace.state, Math.abs(pace.diffDays));
  const percent = Math.round((goal.unitsDone / goal.unitsTotal) * 100);

  return (
    <section className="card pace">
      <div className="pace-head">
        <div className="stack" style={{ gap: 2, minWidth: 0 }}>
          <span className="dim tiny">진행 중인 목표</span>
          <h2 className="pace-title">{goal.title}</h2>
        </div>
        <span className="badge mono">{dday(goal.dDay)}</span>
      </div>

      <div className="pace-progress">
        <div className="pace-progress-label">
          <span className="muted">
            {goal.unitsDone} / {goal.unitsTotal} 단원
          </span>
          <span className="mono strong">{percent}%</span>
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
      </div>

      <div className="pace-foot">
        <span className={view.tone === 'muted' ? 'badge' : 'badge badge-' + view.tone}>
          {view.label}
        </span>
        <p className="pace-next">{pace.nextCheckpoint}</p>
      </div>
    </section>
  );
}
