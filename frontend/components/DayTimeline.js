import Link from 'next/link';
import { IconCheck } from './Icon';

// FR-MAIN-03 오늘의 학습 블록
//
// 블록마다 카드를 띄우면 하루가 조각조각 끊겨 보인다.
// 실제 플래너처럼 시간 축 하나에 매달아 하루를 한 덩어리로 읽히게 한다.
//
// 완료는 여기서 체크하지 않는다 — 타이머로 공부 시간을 기록해야 완료로 저장된다 (FR-STUDY-01/02).
// 화면에서만 체크되고 저장되지 않는 버튼은 사용자를 속인다. 남은 블록은 그 블록으로 타이머를 연다.

export default function DayTimeline({ blocks }) {
  return (
    <ol className="tl">
      {blocks.map((block) => (
        <li key={block.id} className={block.done ? 'tl-item tl-done' : 'tl-item'}>
          <span className="tl-time">{block.start}</span>
          <span className="tl-dot" />
          <div className="tl-row">
            <div className="tl-body">
              <span className="tl-title">{block.subject}</span>
              <span className="tl-sub">
                {block.scope ? `${block.scope} · ` : ''}
                {block.minutes}분
              </span>
            </div>
            {block.done ? (
              <span className="tl-check tl-check-on" aria-label={`${block.subject} 완료`} role="img">
                <IconCheck width={14} height={14} />
              </span>
            ) : (
              <Link className="btn btn-sm" href={`/study?block=${encodeURIComponent(block.id)}`}>
                시작
              </Link>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
