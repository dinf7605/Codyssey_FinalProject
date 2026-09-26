'use client';

import { useState } from 'react';
import Link from 'next/link';
import { IconCheck } from './Icon';
import { canCancelDone, dayKey, hhmm } from '@/lib/planView';

// 저장된 계획의 하루치 블록 (담당 C)
//   FR-PLAN-05 블록 수동 편집 — 메뉴로 옮기기·지우기, PC 에서는 달력 날짜로 끌어다 놓기
//   FR-STUDY-01 시작 → 학습 타이머
//   FR-STUDY-02 완료 취소 — 24시간 안에만
//
// 모양은 DayTimeline 과 같은 시간 축(.tl)을 쓴다. 대시보드는 DayTimeline 을 그대로 쓴다.

function MoveForm({ block, today, deadline, busy, onMove, onCancel }) {
  const [date, setDate] = useState(dayKey(block.start) < today ? today : dayKey(block.start));
  const [time, setTime] = useState(hhmm(block.start));
  return (
    <form
      className="tl-edit"
      onSubmit={(e) => {
        e.preventDefault();
        onMove(block, `${date}T${time}:00`);
      }}
    >
      <label>
        <span className="tiny dim">날짜</span>
        <input className="input" type="date" required value={date} min={today} max={deadline}
          onChange={(e) => setDate(e.target.value)} />
      </label>
      <label>
        <span className="tiny dim">시작</span>
        <input className="input" type="time" required step={600} value={time}
          onChange={(e) => setTime(e.target.value)} />
      </label>
      <div style={{ display: 'flex', gap: 'var(--gap-2)' }}>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>옮기기</button>
        <button type="button" className="btn btn-quiet btn-sm" onClick={onCancel}>취소</button>
      </div>
    </form>
  );
}

export default function PlanDayBlocks({ blocks, today, deadline, busy, onMove, onDelete, onCancelDone, onDragStart, onDragEnd }) {
  const [menu, setMenu] = useState(null);    // 메뉴가 열린 블록 id
  const [mode, setMode] = useState(null);    // null | 'move' | 'delete'

  function close() {
    setMenu(null);
    setMode(null);
  }

  function toggle(id) {
    if (menu === id) {
      close();
    } else {
      setMenu(id);
      setMode(null);
    }
  }

  return (
    <ol className="tl">
      {blocks.map((block) => {
        const open = menu === block.id;
        const editable = !block.done;
        return (
          <li
            key={block.id}
            className={block.done ? 'tl-item tl-done' : 'tl-item'}
            draggable={editable}
            onDragStart={editable ? (e) => {
              e.dataTransfer.setData('text/plain', block.id);
              e.dataTransfer.effectAllowed = 'move';
              onDragStart(block);
            } : undefined}
            onDragEnd={onDragEnd}
          >
            <span className="tl-time">{hhmm(block.start)}</span>
            <span className="tl-dot" />
            <div className="tl-row">
              <div className="tl-body">
                <span className="tl-title">{block.title}</span>
                <span className="tl-sub">
                  {block.minutes}분{block.locked ? ' · 직접 옮김(자동 재조정 제외)' : ''}
                </span>
              </div>
              {block.done ? (
                canCancelDone(block) ? (
                  <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => onCancelDone(block)}>
                    완료 취소
                  </button>
                ) : (
                  <span className="tl-check tl-check-on" role="img" aria-label="완료">
                    <IconCheck width={14} height={14} />
                  </span>
                )
              ) : (
                <div style={{ display: 'flex', gap: 4, flex: 'none' }}>
                  <Link className="btn btn-sm" href={`/study?block=${encodeURIComponent(block.id)}`}>시작</Link>
                  <button type="button" className="btn btn-quiet btn-sm" aria-expanded={open}
                    aria-label={`${block.title} 편집`} onClick={() => toggle(block.id)}>
                    ⋯
                  </button>
                </div>
              )}
            </div>

            {open && mode === null && (
              <div className="tl-edit tl-edit-row">
                <button type="button" className="btn btn-sm" onClick={() => setMode('move')}>옮기기</button>
                <button type="button" className="btn btn-sm" onClick={() => setMode('delete')}>지우기</button>
              </div>
            )}
            {open && mode === 'move' && (
              <MoveForm block={block} today={today} deadline={deadline} busy={busy}
                onMove={(b, start) => { onMove(b, start); close(); }} onCancel={close} />
            )}
            {open && mode === 'delete' && (
              <div className="tl-edit">
                <p className="tiny">이 블록을 일정에서 지울까요? 이 단원은 다시 배치되지 않아요.</p>
                <div style={{ display: 'flex', gap: 'var(--gap-2)' }}>
                  <button type="button" className="btn btn-sm" disabled={busy} onClick={() => { onDelete(block); close(); }}>
                    지우기
                  </button>
                  <button type="button" className="btn btn-quiet btn-sm" onClick={close}>취소</button>
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
