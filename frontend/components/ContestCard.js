import Link from 'next/link';
import { AiBadge } from './AiNotice';
import { dday } from '@/lib/ui';

// FR-CONT-04 추천 / FR-CONT-05 추천 이유
// 카드로 띄우지 않고 규칙선으로 나눈 목록으로 둔다 — 길어져도 화면이 소란스럽지 않다.

export default function ContestCard({ contest }) {
  const urgent = contest.dDay <= 7;

  return (
    <li>
      <Link href={'/contests/' + contest.id} className="ct">
        <div className="ct-top">
          <span className={urgent ? 'tag tag-late' : 'tag tag-accent'}>{dday(contest.dDay)}</span>
          <span className="micro dim">{contest.field}</span>
          {contest.aiGenerated && <AiBadge />}
        </div>
        <h3 className="ct-title">{contest.title}</h3>
        <p className="ct-host">
          {contest.host} · 마감 {contest.deadline}
        </p>
        {contest.reason && <p className="ct-reason">{contest.reason}</p>}
      </Link>
    </li>
  );
}
