'use client';

import { useEffect, useRef, useState } from 'react';
import { todayBlocks } from '@/lib/mock';

// FR-STUDY-01 학습 타이머 / FR-STUDY-02 블록 완료 처리 / FR-STUDY-05 학습 메모
// 5분 미만은 기록하지 않는다.

function format(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, '0');
  const s = String(sec % 60).padStart(2, '0');
  return m + ':' + s;
}

export default function StudyPage() {
  const block = todayBlocks.find((b) => !b.done) || todayBlocks[0];
  const [seconds, setSeconds] = useState(0);
  const [running, setRunning] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (running) {
      timer.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    }
    return () => clearInterval(timer.current);
  }, [running]);

  const tooShort = seconds < 300;

  return (
    <>
      <header className="stack" style={{ gap: 4 }}>
        <h1 style={{ fontSize: 20 }}>학습</h1>
        <p className="muted tiny">{block.subject} · {block.scope}</p>
      </header>

      <section className="panel" style={{ padding: 'var(--gap-6) var(--gap-4)' }}>
        <p className="timer">{format(seconds)}</p>
        <p className="dim tiny" style={{ textAlign: 'center', marginTop: 6 }}>
          예상 {block.minutes}분
        </p>

        <div style={{ display: 'flex', gap: 'var(--gap-2)', marginTop: 'var(--gap-5)' }}>
          <button
            type="button"
            className={running ? 'btn' : 'btn btn-primary'}
            onClick={() => setRunning((r) => !r)}
          >
            {running ? '일시정지' : seconds === 0 ? '시작' : '이어서'}
          </button>
          <button type="button" className="btn" disabled={tooShort}>
            완료
          </button>
        </div>

        {tooShort && seconds > 0 && (
          <p className="hint" style={{ marginTop: 'var(--gap-3)', textAlign: 'center' }}>
            5분 이상 학습해야 기록됩니다
          </p>
        )}
      </section>

      <section>
        <div className="sec-head">
          <h2>학습 메모</h2>
          <span className="dim tiny">선택</span>
        </div>
        <div className="field">
          <textarea
            className="input"
            rows={3}
            maxLength={200}
            placeholder="오늘 이해가 안 된 부분을 200자까지 남길 수 있어요"
            style={{ minHeight: 88, padding: 'var(--gap-3)', resize: 'vertical' }}
          />
          <p className="hint">메모를 비워도 완료 처리에는 영향이 없습니다</p>
        </div>
      </section>
    </>
  );
}
