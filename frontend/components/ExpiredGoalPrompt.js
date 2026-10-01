'use client';

import { useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { ddayOf } from '@/lib/planView';
import { notifyPlanChanged } from '@/lib/usePlan';

// FR-MAIN-04 — 목표 기한이 지나면(D+) 목표를 끝낼지 묻는다. 대시보드에서 기한이 지난 목표마다 한 번씩.
// '나중에'를 고르면 이 탭에서는 다시 묻지 않는다. 종료해도 학습 기록·통계는 남는다 (FR-MY-02).

const LATER_KEY = 'sp_expired_goal_later';

function laterIds() {
  try { return JSON.parse(window.sessionStorage.getItem(LATER_KEY) || '[]'); } catch { return []; }
}

export default function ExpiredGoalPrompt({ plans, today }) {
  const [later, setLater] = useState(() => (typeof window === 'undefined' ? [] : laterIds()));
  const [state, setState] = useState({ pending: false, error: '' });
  const plan = plans.find((p) => ddayOf(p.deadline, today) < 0 && !later.includes(p.plan_id));
  if (!plan) return null;
  const over = Math.abs(ddayOf(plan.deadline, today));

  function postpone() {
    const next = [...later, plan.plan_id];
    try { window.sessionStorage.setItem(LATER_KEY, JSON.stringify(next)); } catch { /* 이번만 숨긴다 */ }
    setLater(next);
  }

  async function end() {
    setState({ pending: true, error: '' });
    try {
      await api.plan.archive(plan.plan_id);
      setState({ pending: false, error: '' });
      notifyPlanChanged();
    } catch (err) {
      setState({ pending: false, error: err.message || '목표를 끝내지 못했어요.' });
    }
  }

  return (
    <section className="panel stack" role="alertdialog" aria-labelledby="expired-goal-title"
      style={{ gap: 8, padding: 'var(--gap-3)', borderColor: 'var(--late)' }}>
      <h2 id="expired-goal-title" style={{ fontSize: 15, margin: 0 }}>
        &lsquo;{plan.goal_title}&rsquo; 기한이 {over}일 지났어요 (D+{over})
      </h2>
      <p className="tiny muted" style={{ margin: 0 }}>
        목표를 끝낼까요? 남은 블록은 일정에서 빠지고, 지금까지의 학습 기록과 통계는 그대로 남아요.
        시험·마감이 미뤄졌다면 계획을 다시 만들어 기한을 늘릴 수 있어요.
      </p>
      {state.error && <p className="hint hint-error" role="alert" style={{ margin: 0 }}>{state.error}</p>}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-sm btn-primary" disabled={state.pending} onClick={end}>
          {state.pending ? '끝내는 중…' : '목표 종료'}
        </button>
        <Link className="btn btn-sm" href="/schedule#plan-builder">기한 늘려 다시 만들기</Link>
        <button type="button" className="btn btn-sm btn-quiet" disabled={state.pending} onClick={postpone}>나중에</button>
      </div>
    </section>
  );
}
