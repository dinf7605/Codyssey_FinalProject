'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import EmptyState from './EmptyState';
import PlanDayBlocks from './PlanDayBlocks';
import SectionTitle from './SectionTitle';
import { api } from '@/lib/api';
import { notifyPlanChanged, usePlan } from '@/lib/usePlan';
import {
  VIOLATION_LABEL, WEEKDAY_MON, addDays, addMonths, blockState, blocksByDay, dayKey, dayNum, ddayOf,
  hhmm, kstToday, monthGrid, monthLabel, weekOf, whenLabel,
} from '@/lib/planView';

// FR-PLAN-04 일정 조회 — 확정한 계획을 주·월 단위로 본다 (담당 C)
// FR-PLAN-05 블록 수동 편집 — 날짜 칸으로 끌어다 놓거나(PC) 블록 메뉴로 옮기기·지우기
// FR-PLAN-06 지난 미완료 블록은 매일 03:00 에 다시 놓인다 — 기다리지 않고 지금 놓을 수도 있다
//
// 완료 · 미완료 · 예정을 색으로 나눈다. 조회는 목표 기한까지만.

const DOT = { done: 'dot dot-done', miss: 'dot dot-miss', plan: 'dot' };

function Day({ date, label, today, selected, blocks, disabled, dropping, onPick, onDrop }) {
  const [over, setOver] = useState(false);
  if (!date) return <div className="cal-day cal-out" aria-hidden="true" />;
  const canDrop = dropping && !disabled && date >= today;
  const cls = [
    'cal-day', date === today && 'cal-today', date === selected && 'cal-picked', disabled && 'cal-out',
    canDrop && over && 'cal-drop',
  ].filter(Boolean).join(' ');
  return (
    <button
      type="button"
      className={cls}
      disabled={disabled}
      onClick={() => onPick(date)}
      aria-pressed={date === selected}
      aria-label={`${date} 블록 ${blocks.length}개`}
      onDragOver={canDrop ? (e) => { e.preventDefault(); setOver(true); } : undefined}
      onDragLeave={() => setOver(false)}
      onDrop={canDrop ? (e) => { e.preventDefault(); setOver(false); onDrop(date); } : undefined}
    >
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
  const [dragging, setDragging] = useState(null);
  const [busy, setBusy] = useState(false);
  // { kind: 'ok' | 'error', text } 또는 { kind: 'warn', block, start, violations, forceable }
  const [notice, setNotice] = useState(null);

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
        description="아래에서 학습 계획을 만들고 '이 계획으로 확정'을 누르면 여기에 일정이 나옵니다."
      />
    );
  }

  const deadline = plan.deadline;
  const firstDay = plan.blocks.length ? plan.blocks.map((b) => dayKey(b.start)).sort()[0] : today;
  const minDay = firstDay < today ? firstDay : today;
  const clamp = (key) => (key < minDay ? minDay : key > deadline ? deadline : key);
  const selected = clamp(picked || today);

  const days = weekOf(selected);
  const canPrev = view === 'week' ? days[0] > minDay : `${selected.slice(0, 7)}-01` > minDay;
  const canNext = view === 'week' ? days[6] < deadline : addMonths(selected, 1) <= deadline;
  const missed = plan.blocks.filter((b) => !b.done && !b.locked && dayKey(b.start) < today).length;

  function move(step) {
    setPicked(clamp(view === 'week' ? addDays(selected, step * 7) : addMonths(selected, step)));
  }

  async function act(work) {
    setBusy(true);
    setNotice(null);
    try {
      await work();
    } catch (err) {
      setNotice({ kind: 'error', text: err.message || '처리하지 못했어요.' });
    } finally {
      setBusy(false);
    }
  }

  const moveBlock = (block, start, force = false) =>
    act(async () => {
      const res = await api.plan.moveBlock(block.id, { start, force });
      if (res.applied) {
        setNotice({ kind: 'ok', text: `‘${block.title}’ 블록을 ${whenLabel(start)}(으)로 옮겼어요. 이제 자동 재조정에서 빠져요.` });
        setPicked(dayKey(start));
        notifyPlanChanged();
      } else {
        setNotice({ kind: 'warn', block, start, violations: res.violations, forceable: res.forceable });
      }
    });

  const deleteBlock = (block) =>
    act(async () => {
      await api.plan.deleteBlock(block.id);
      setNotice({ kind: 'ok', text: `‘${block.title}’ 블록을 지웠어요.` });
      notifyPlanChanged();
    });

  const cancelDone = (block) =>
    act(async () => {
      await api.study.cancelDone(block.id);
      setNotice({ kind: 'ok', text: `‘${block.title}’ 완료를 취소했어요. 공부한 시간 기록은 그대로 남아요.` });
      notifyPlanChanged();
    });

  const replanNow = () =>
    act(async () => {
      const res = await api.plan.replanNow();
      setNotice({ kind: 'ok', text: res.summary });
      notifyPlanChanged();
    });

  // 끌어다 놓으면 시각은 그대로, 날짜만 바꾼다
  const dropOn = (date) => {
    if (dragging) moveBlock(dragging, `${date}T${hhmm(dragging.start)}:00`);
    setDragging(null);
  };

  const dayProps = (date) => ({
    date,
    today,
    selected,
    blocks: (date && byDay.get(date)) || [],
    disabled: !date || date < minDay || date > deadline,
    dropping: Boolean(dragging),
    onPick: setPicked,
    onDrop: dropOn,
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

      {missed > 0 && (
        <div className="progress" role="note">
          <b>지난 미완료 블록 {missed}개</b>
          <p className="muted tiny">매일 새벽 3시에 남은 기간으로 자동으로 다시 놓아요. 기다리지 않고 지금 놓을 수도 있어요.</p>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={replanNow}>지금 다시 놓기</button>
        </div>
      )}

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

      {notice?.kind === 'warn' && (
        <div className="progress" role="alertdialog" aria-label="옮기기 확인">
          <b>{notice.forceable ? '옮기면 이런 문제가 생겨요' : '이 자리로는 옮길 수 없어요'}</b>
          <ul className="progress-log warn-log">
            {[...new Set(notice.violations.map((v) => VIOLATION_LABEL[v.kind] || v.detail))].map((text) => (
              <li key={text}><span>{text}</span></li>
            ))}
          </ul>
          <div style={{ display: 'flex', gap: 'var(--gap-2)' }}>
            {notice.forceable && (
              <button type="button" className="btn btn-sm" disabled={busy}
                onClick={() => moveBlock(notice.block, notice.start, true)}>
                그래도 옮기기
              </button>
            )}
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => setNotice(null)}>취소</button>
          </div>
        </div>
      )}
      {notice?.kind === 'ok' && <p className="hint" role="status" style={{ color: 'var(--ok)' }}>{notice.text}</p>}
      {notice?.kind === 'error' && <p className="hint hint-error" role="alert">{notice.text}</p>}

      <div className="stack" style={{ gap: 'var(--gap-2)' }}>
        <SectionTitle>
          {selected === today ? '오늘 블록' : `${Number(selected.slice(5, 7))}/${dayNum(selected)} 블록`}
        </SectionTitle>
        {dayBlocks.length ? (
          <PlanDayBlocks
            key={selected}
            blocks={dayBlocks}
            today={today}
            deadline={deadline}
            busy={busy}
            onMove={moveBlock}
            onDelete={deleteBlock}
            onCancelDone={cancelDone}
            onDragStart={setDragging}
            onDragEnd={() => setDragging(null)}
          />
        ) : (
          <p className="hint">이날은 배치된 블록이 없습니다.</p>
        )}
        {dayBlocks.some((b) => !b.done) && (
          <p className="hint">PC 에서는 블록을 위 달력의 날짜로 끌어다 놓아도 옮겨져요. 직접 옮긴 블록은 자동 재조정에서 빠져요.</p>
        )}
      </div>
    </div>
  );
}
