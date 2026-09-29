import Link from 'next/link';
import { AiBadge } from './AiNotice';
import { dday } from '@/lib/ui';

// FR-CONT-04 추천 / FR-CONT-05 추천 이유
// 카드로 띄우지 않고 규칙선으로 나눈 목록으로 둔다 — 길어져도 화면이 소란스럽지 않다.

export default function ContestCard({ contest }) {
  const urgent = contest.dDay !== null && contest.dDay <= 7;

  return (
    <li>
      <Link href={'/contests/' + contest.id} className="ct">
        <div className="ct-top">
          {contest.source === 'wevity' ? <span className="micro dim">출처: 위비티</span> : (
            <>
              {contest.dDay !== null && <span className={urgent ? 'tag tag-late' : 'tag tag-accent'}>{dday(contest.dDay)}</span>}
              <span className="micro dim">{contest.field}</span>
            </>
          )}
          {contest.aiGenerated && <AiBadge />}
          {contest.recommended && !contest.aiGenerated && <span className="pill">키워드 추천</span>}
        </div>
        <h3 className="ct-title">{contest.title}</h3>
        <p className="ct-host">
          {contest.source === 'wevity' ? '위비티에서 공고 확인하기 ↗' : `${contest.host} · 마감 ${contest.deadline}`}
        </p>
        {contest.reason && <p className="ct-reason">{contest.reason}</p>}
      </Link>
    </li>
  );
}
