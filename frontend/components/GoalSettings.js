'use client';

import { useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { BANDS, slotsFromExploration, slotsHours } from '@/lib/planInput';
import { notifyPlanChanged } from '@/lib/usePlan';

// FR-MY-01 가용 시간 수정 · FR-MY-02 목표 관리(종료·바꾸기) · FR-PLAN-08 내 캘린더로 내보내기 — 마이페이지
// 시간을 바꾸면 아직 안 한 앞으로의 블록이 새 시간에 다시 놓인다 (PUT /plan/{id}/availability).
// 다 들어가지 않으면 서버가 아무것도 바꾸지 않고 이유를 알려 준다.

const DAYS = ['월', '화', '수', '목', '금', '토', '일'];
const SUNDAY = 6;

// 저장된 시간표 → 온보딩과 같은 '시간대-요일' 칸. 칸과 딱 맞지 않는 시간은 칸으로 옮기지 못해 따로 알린다
function cellsOf(availability) {
  const cells = {};
  let odd = 0;
  for (const slot of availability?.slots || []) {
    const band = Object.keys(BANDS).find((b) => BANDS[b].start === slot.start && BANDS[b].end === slot.end);
    if (band) cells[`${band}-${DAYS[slot.weekday]}`] = true;
    else odd += 1;
  }
  return { cells, odd };
}

function StudyTimeEditor({ plan, onDone }) {
  const initial = cellsOf(plan.availability);
  const [cells, setCells] = useState(initial.cells);
  const [state, setState] = useState({ pending: false, error: '' });
  const slots = slotsFromExploration(cells);

  async function save() {
    setState({ pending: true, error: '' });
    try {
      const sunday = slots.some((s) => s.weekday === SUNDAY);
      // 일요일을 직접 고르면 쉬는 날로 두지 않는다 (기본은 일요일 휴식)
      const res = await api.plan.changeAvailability(plan.plan_id, sunday ? { slots, rest_weekday: null } : { slots });
      notifyPlanChanged();
      onDone(`공부 시간을 바꿨어요. 블록 ${res.moved}개를 새 시간에 다시 놓았어요.`);
    } catch (err) {
      setState({ pending: false, error: err.message || '바꾸지 못했어요. 잠시 후 다시 시도해 주세요.' });
    }
  }

  return (
    <div className="stack" style={{ gap: 10, marginTop: 8 }}>
      {initial.odd > 0 && (
        <p className="hint">지금 시간표에는 칸으로 나타낼 수 없는 시간이 {initial.odd}개 있어요. 저장하면 아래 고른 칸으로 바뀝니다.</p>
      )}
      <div className="db-scroll" tabIndex={0} aria-label="요일별 공부 가능 시간">
        <table className="db-table">
          <thead>
            <tr><th scope="col">시간대</th>{DAYS.map((d) => <th key={d} scope="col">{d}</th>)}</tr>
          </thead>
          <tbody>
            {Object.entries(BANDS).map(([band, { start, end }]) => (
              <tr key={band}>
                <th scope="row" className="tiny">{band}<br /><span className="micro dim">{start}–{end}</span></th>
                {DAYS.map((d) => {
                  const key = `${band}-${d}`;
                  return (
                    <td key={d} style={{ textAlign: 'center' }}>
                      <input type="checkbox" aria-label={`${d}요일 ${band}`} checked={Boolean(cells[key])}
                        onChange={(e) => setCells((old) => ({ ...old, [key]: e.target.checked }))} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tiny muted" style={{ margin: 0 }}>주 {slotsHours(slots)}시간 · 완료한 블록과 직접 옮긴 블록은 그대로 둡니다</p>
      {state.error && <p className="hint hint-error" role="alert">{state.error}</p>}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-sm btn-primary" onClick={save} disabled={state.pending || !slots.length}>
          {state.pending ? '다시 놓는 중…' : '이 시간으로 바꾸기'}
        </button>
        <button type="button" className="btn btn-sm btn-quiet" onClick={() => onDone('')} disabled={state.pending}>취소</button>
      </div>
    </div>
  );
}

export default function GoalSettings({ plans }) {
  const [open, setOpen] = useState(null);       // 시간 편집을 연 계획 id
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [ending, setEnding] = useState(null);

  // FR-PLAN-08 — 오늘 이후의 블록을 .ics 로 받아 구글·애플·아웃룩 캘린더에서 가져오게 한다
  async function exportCalendar(plan) {
    setError('');
    try {
      const blob = await api.plan.calendarFile(plan.plan_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `studypace-${plan.goal_title.replace(/[\\/:*?"<>|\s]+/g, '_')}.ics`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('캘린더 파일을 받았어요. 구글 캘린더는 설정 → 가져오기·내보내기 → 가져오기에서 이 파일을 고르면 됩니다.');
    } catch (err) {
      setError(err.message || '캘린더 파일을 만들지 못했어요.');
    }
  }

  async function endGoal(plan) {
    if (!window.confirm(`'${plan.goal_title}' 목표를 종료할까요? 남은 블록은 일정에서 사라지고, 지금까지의 학습 기록은 남습니다.`)) return;
    setEnding(plan.plan_id);
    setError('');
    try {
      await api.plan.archive(plan.plan_id);
      setMessage(`'${plan.goal_title}' 목표를 종료했어요.`);
      notifyPlanChanged();
    } catch (err) {
      setError(err.message || '목표를 종료하지 못했어요.');
    } finally {
      setEnding(null);
    }
  }

  if (!plans.length) return null;

  return (
    <div className="stack" style={{ gap: 8 }}>
      {plans.map((p) => (
        <div key={p.plan_id} className="panel" style={{ padding: 'var(--gap-3)' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <b style={{ flex: 1, minWidth: 120 }}>{p.goal_title}</b>
            <button type="button" className="btn btn-sm" aria-expanded={open === p.plan_id}
              onClick={() => { setOpen(open === p.plan_id ? null : p.plan_id); setMessage(''); }}>
              공부 시간 바꾸기
            </button>
            <button type="button" className="btn btn-sm" onClick={() => exportCalendar(p)}>
              내 캘린더에 넣기 (.ics)
            </button>
            <button type="button" className="btn btn-sm btn-quiet" disabled={ending === p.plan_id} onClick={() => endGoal(p)}>
              {ending === p.plan_id ? '종료 중…' : '목표 종료'}
            </button>
          </div>
          {open === p.plan_id && (
            <StudyTimeEditor plan={p} onDone={(text) => { setOpen(null); setMessage(text); }} />
          )}
        </div>
      ))}
      {message && <p className="hint" role="status">{message}</p>}
      {error && <p className="hint hint-error" role="alert">{error}</p>}
      <p className="hint">
        다른 목표로 바꾸려면 지금 목표를 종료하고 <Link href="/onboarding" className="accent-text">새 목표 찾기</Link>에서 고르세요.
      </p>
    </div>
  );
}
