'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

// FR-ADMIN-02 — 오늘 AI 예상 사용액과 하루 한도 (backend/services/ai_budget.py)
// 80% 를 넘으면 비회원 AI 추천을 먼저 막고, 100% 면 새 AI 호출을 막아 규칙·템플릿으로 대신한다.
// 게이트웨이가 청구액을 주지 않아 기록 수 × 모델별 1회 예상 비용으로 어림한 값이다.

const STATE = {
  ok: { label: '정상', cls: 'pill pill-ok', text: '' },
  warning: { label: '경고', cls: 'pill', text: '한도의 80%를 넘어 비회원 AI 추천을 막았습니다. 회원 기능은 계속 동작합니다.' },
  blocked: { label: '차단', cls: 'pill pill-late', text: '오늘 한도에 닿아 새 AI 호출을 막았습니다. 학습 분해·추천은 규칙과 템플릿으로 대신합니다.' },
  off: { label: '한도 없음', cls: 'pill', text: 'AI_DAILY_BUDGET_USD 가 0 이하라 한도를 쓰지 않습니다.' },
};

const FEATURE = { 'plan.decompose': '학습 분해', 'goal.match': '목표 추천', 'contest.recommend': '공모전 추천' };

export default function AdminAiBudget() {
  const [result, setResult] = useState(null);

  useEffect(() => {
    let alive = true;
    api.admin.aiBudget().then(
      (data) => alive && setResult({ data }),
      (err) => alive && setResult({ error: err.status === 403 ? '관리자 권한이 필요합니다.' : 'AI 사용량을 불러오지 못했습니다.' }),
    );
    return () => { alive = false; };
  }, []);

  if (!result) return <p role="status" className="hint">오늘 AI 사용량을 확인하고 있습니다.</p>;
  if (result.error) return <p role="alert" className="hint hint-error">{result.error}</p>;
  const d = result.data;
  const view = STATE[d.state] || STATE.ok;
  const percent = d.limit_usd > 0 ? Math.min(100, Math.round((d.spent_usd / d.limit_usd) * 100)) : 0;

  return (
    <div className="stack" style={{ gap: 8 }} role={d.state === 'ok' ? undefined : 'alert'}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <span className={view.cls}>{view.label}</span>
        <span className="mono" style={{ fontWeight: 600 }}>${d.spent_usd.toFixed(2)}</span>
        <span className="tiny muted">/ 하루 ${d.limit_usd.toFixed(2)} · 오늘 {d.calls}회 (예상치)</span>
      </div>
      {d.limit_usd > 0 && (
        <div className="bar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="오늘 AI 예상 사용액">
          <div className="bar-fill" style={{ width: `${percent}%` }} />
        </div>
      )}
      {view.text && <p className="hint" style={{ margin: 0 }}>{view.text}</p>}
      {Object.keys(d.by_feature || {}).length > 0 && (
        <p className="tiny muted" style={{ margin: 0 }}>
          {Object.entries(d.by_feature).map(([k, n]) => `${FEATURE[k] || k} ${n}회`).join(' · ')}
        </p>
      )}
    </div>
  );
}
