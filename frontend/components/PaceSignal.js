'use client';

import { useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { dayNum, WEEKDAY_MON, weekdayMon } from '@/lib/planView';
import { paceView, dday } from '@/lib/ui';
import { notifyPlanChanged } from '@/lib/usePlan';

// FR-PACE-04 진도 신호등 + FR-MAIN-04 목표 진행률
// FR-PACE-01 중간 목표 — 다음 체크포인트 '언제까지 어디까지' (lib/pace.js milestones)
// FR-PACE-03 뒤처지면 무엇을 바꿀 수 있는지 안내하고 바로 할 수 있게 한다
// 색만으로 상태를 구분하지 않고 항상 문구를 함께 보여준다 (NFR-A11Y-01).

const dateLabel = (key) => `${Number(key.slice(5, 7))}/${dayNum(key)}(${WEEKDAY_MON[weekdayMon(key)]})`;

function LateAdvice({ diffDays }) {
  const [state, setState] = useState({ pending: false, text: '' });

  async function replanNow() {
    setState({ pending: true, text: '' });
    try {
      const res = await api.plan.replanNow();
      notifyPlanChanged();
      setState({ pending: false, text: res?.summary || '지난 블록을 남은 기간에 다시 놓았어요.' });
    } catch (err) {
      setState({ pending: false, text: err.message || '지금은 다시 맞추지 못했어요. 밤사이 자동으로 다시 맞춰 드려요.' });
    }
  }

  return (
    <div className="panel stack" style={{ gap: 8, padding: 'var(--gap-3)', marginTop: 4 }} role="note">
      <p className="tiny" style={{ margin: 0 }}>
        계획보다 {diffDays}일 늦어졌어요. 이렇게 맞춰 볼 수 있어요.
      </p>
      <ul className="tiny muted stack" style={{ gap: 2, paddingLeft: 18, margin: 0 }}>
        <li>지난 블록을 남은 빈 시간에 지금 다시 놓기 (밤 3시에도 자동으로 해요)</li>
        <li>공부 가능 시간을 늘려 앞으로의 블록을 촘촘하게 놓기</li>
        <li>일정에서 블록을 직접 옮기거나 지우기</li>
      </ul>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-sm btn-primary" onClick={replanNow} disabled={state.pending}>
          {state.pending ? '맞추는 중…' : '지금 다시 맞추기'}
        </button>
        <Link className="btn btn-sm" href="/mypage#goal-settings">공부 시간 늘리기</Link>
        <Link className="btn btn-sm btn-quiet" href="/schedule">일정에서 옮기기</Link>
      </div>
      {state.text && <p className="hint" role="status" style={{ margin: 0 }}>{state.text}</p>}
    </div>
  );
}

export default function PaceSignal({ goal, pace, milestones = [] }) {
  const view = paceView(pace.state, Math.abs(pace.diffDays));
  const percent = goal.unitsTotal ? Math.round((goal.unitsDone / goal.unitsTotal) * 100) : 0;
  const passed = milestones.filter((m) => m.done).length;
  const next = milestones.find((m) => !m.done);

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
          <span className="mono" style={{ fontSize: '14px', fontWeight: 600 }}>{percent}%</span>
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

        {next && (
          <p className="tiny" style={{ margin: 0 }}>
            <b>다음 중간 목표</b> · {dateLabel(next.due)}까지 ‘{next.title}’까지
            <span className="muted"> (체크포인트 {passed}/{milestones.length} 통과)</span>
          </p>
        )}

        {pace.state === 'late' && <LateAdvice diffDays={Math.abs(pace.diffDays)} />}
      </div>
    </section>
  );
}
