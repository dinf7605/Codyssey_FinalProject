'use client';

import { useState } from 'react';

// FR-MAIN-03 오늘의 학습 블록 + FR-STUDY-02 블록 완료 처리

export default function BlockCard({ block, onToggle }) {
  const [done, setDone] = useState(block.done);

  function toggle() {
    const next = !done;
    setDone(next);
    onToggle?.(block.id, next);
  }

  return (
    <li className={done ? 'card block block-done' : 'card block'}>
      <div className="block-time mono">
        <span className="block-start">{block.start}</span>
        <span className="block-min">{block.minutes}분</span>
      </div>

      <div className="block-rule" />

      <div className="stack block-body">
        <span className="block-subject">{block.subject}</span>
        <span className="block-scope">{block.scope}</span>
      </div>

      <button
        type="button"
        onClick={toggle}
        aria-pressed={done}
        aria-label={done ? block.subject + ' 완료 취소' : block.subject + ' 완료 처리'}
        className="block-check"
      >
        ✓
      </button>
    </li>
  );
}
