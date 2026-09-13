'use client';

import { useState } from 'react';
import { IconCheck } from './Icon';

// FR-MAIN-03 오늘의 학습 블록 / FR-STUDY-02 완료 처리
//
// 블록마다 카드를 띄우면 하루가 조각조각 끊겨 보인다.
// 실제 플래너처럼 시간 축 하나에 매달아 하루를 한 덩어리로 읽히게 한다.

export default function DayTimeline({ blocks }) {
  const [done, setDone] = useState(() => new Set(blocks.filter((b) => b.done).map((b) => b.id)));

  function toggle(id) {
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <ol className="tl">
      {blocks.map((block) => {
        const isDone = done.has(block.id);
        return (
          <li key={block.id} className={isDone ? 'tl-item tl-done' : 'tl-item'}>
            <span className="tl-time">{block.start}</span>
            <span className="tl-dot" />
            <div className="tl-row">
              <div className="tl-body">
                <span className="tl-title">{block.subject}</span>
                <span className="tl-sub">
                  {block.scope} · {block.minutes}분
                </span>
              </div>
              <button
                type="button"
                className="tl-check"
                aria-pressed={isDone}
                aria-label={isDone ? block.subject + ' 완료 취소' : block.subject + ' 완료 처리'}
                onClick={() => toggle(block.id)}
              >
                <IconCheck width={14} height={14} />
              </button>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
