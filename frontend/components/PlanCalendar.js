'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import DayTimeline from './DayTimeline';
import EmptyState from './EmptyState';
import SectionTitle from './SectionTitle';
import { usePlan } from '@/lib/usePlan';
import {
  WEEKDAY_MON, addDays, addMonths, blockState, blocksByDay, dayNum, ddayOf, kstToday,
  monthGrid, monthLabel, toTimeline, weekOf,
} from '@/lib/planView';

// FR-PLAN-04 일정 조회 — 확정한 계획을 주·월 단위로 본다 (담당 C)
//
// 완료 · 미완료 · 예정을 색으로 나눈다. 조회는 목표 기한까지만.
// 날짜를 누르면 그날 블록이 아래에 나오고, 블록의 "시작"은 학습 타이머로 간다.

const DOT = { done: 'dot dot-done', miss: 'dot dot-miss', plan: 'dot' };

function Day({ date, label, today, selected, blocks, disabled, onPick }) {
  if (!date) return <div className="cal-day cal-out" aria-hidden="true" />;
  const cls = ['cal-day', date === today && 'cal-today', date === selected && 'cal-picked', disabled && 'cal-out']
    .filter(Boolean).join(' ');
  return (
    <button type="button" className={cls} disabled={disabled} onClick={() => onPick(date)}
      aria-pressed={date === selected} aria-label={`${date} 블록 ${blocks.length}개`}>
      {label && <span className="day-name">{label}</span>}
      <span className="day-num">{dayNum(date)}</span>
      <span className="cal-dots">
        {blocks.map((b) => <i key={b.id} className={DOT[blockState(b, today)]} />)}
      </span>
    </button>
  );
}

export default function PlanCalendar() {
  const { status, plan, error, reload } = usePlan();
  const today = kstToday();
  const [view, setView] = useState('week'); // week | month
  const [picked, setPicked] = useState(null);

  const byDay = useMemo(() => (plan ? blocksByDay(plan.blocks) : new Map()), [plan]);

  if (status === 'loading') {
    return <p className="hint">계획을 불러오는 중…</p>;
  }
  if (status === 'anon') {
    return (
      <EmptyState
        title="로그인하면 확정한 일정을 볼 수 있어요"
        description="계획 만들기는 로그인 없이도 해 볼 수 있습니다. 저장과 일정 보기는 로그인 후에 됩니다."
        action={<Link className="btn btn-primary btn-sm" href="/login?next=/schedule">로그인</Link>}
      />
    );
  }
  if (status === 'error') {
    return (
      <EmptyState
        title="일정을 불러오지 못했습니다"
        description={error}
        action={<button type="button" className="btn btn-sm" onClick={reload}>다시 시도</button>}
      />
    );
  }
  if (status === 'empty') {
    return (
      <EmptyState
        title="아직 확정한 계획이 없어요"
        description="위에서 학습 계획을 만들고 '이 계획으로 확정'을 누르면 여기에 일정이 나옵니다."
      />
    );
  }

  const deadline = plan.deadline;
  const firstDay = plan.blocks.length ? plan.blocks.map((b) => b.start.slice(0, 10)).sort()[0] : today;
  const minDay = firstDay < today ? firstDay : today;
  const clamp = (key) => (key < minDay ? minDay : key > deadline ? deadline : key);
  const selected = clamp(picked || today);

  const days = weekOf(selected);
  const canPrev = view === 'week' ? days[0] > minDay : `${selected.slice(0, 7)}-01` > minDay;
  const canNext = view === 'week' ? days[6] < deadline : addMonths(selected, 1) <= deadline;

  function move(step) {
    setPicked(clamp(view === 'week' ? addDays(selected, step * 7) : addMonths(selected, step)));
  }

  const dayProps = (date) => ({
    date,
    today,
    selected,
    blocks: (date && byDay.get(date)) || [],
    disabled: !date || date < minDay || date > deadline,
    onPick: setPicked,
  });

  const dayBlocks = byDay.get(selected) || [];
  const doneCount = plan.blocks.filter((b) => b.done).length;
  const dday = ddayOf(deadline, today);

  return (
    <div className="stack" style={{ gap: 'var(--gap-4)' }}>
      <div className="row" style={{ borderBottom: 0, paddingBottom: 0 }}>
        <div className="row-main">
          <b>{plan.goal_title}</b>
          <span>
            {dday >= 0 ? `D-${dday}` : `기한 ${-dday}일 지남`} · 블록 {doneCount}/{plan.blocks.length} 완료
          </span>
        </div>
        <div className="cal-seg" role="group" aria-label="보기 전환">
          <button type="button" className="chip" aria-pressed={view === 'week'} onClick={() => setView('week')}>주</button>
          <button type="button" className="chip" aria-pressed={view === 'month'} onClick={() => setView('month')}>월</button>
        </div>
      </div>

      <div className="stack" style={{ gap: 'var(--gap-3)' }}>
        <div className="cal-nav">
          <button type="button" className="btn btn-quiet btn-sm" disabled={!canPrev} onClick={() => move(-1)} aria-label="이전">‹</button>
          <b>{view === 'week' ? `${monthLabel(days[0])} ${dayNum(days[0])}일 주` : monthLabel(selected)}</b>
          <button type="button" className="btn btn-quiet btn-sm" disabled={!canNext} onClick={() => move(1)} aria-label="다음">›</button>
        </div>

        {view === 'week' ? (
          <div className="week">
            {days.map((d, i) => <Day key={d} label={WEEKDAY_MON[i]} {...dayProps(d)} />)}
          </div>
        ) : (
          <div className="cal-month">
            {WEEKDAY_MON.map((w) => <span key={w} className="day-name cal-head">{w}</span>)}
            {monthGrid(selected).flat().map((d, i) => <Day key={d || `x${i}`} {...dayProps(d)} />)}
          </div>
        )}
        <p className="hint cal-legend">
          <span><i className="dot dot-done" /> 완료</span>
          <span><i className="dot dot-miss" /> 미완료</span>
          <span><i className="dot" /> 예정</span>
          <span>기한 {deadline}까지</span>
        </p>
      </div>

      <div className="stack" style={{ gap: 'var(--gap-2)' }}>
        <SectionTitle>
          {selected === today ? '오늘 블록' : `${Number(selected.slice(5, 7))}/${dayNum(selected)} 블록`}
        </SectionTitle>
        {dayBlocks.length ? (
          <DayTimeline blocks={dayBlocks.map(toTimeline)} studyLinks />
        ) : (
          <p className="hint">이날은 배치된 블록이 없습니다.</p>
        )}
      </div>
    </div>
  );
}
