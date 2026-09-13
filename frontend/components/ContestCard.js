import Link from 'next/link';
import { AiBadge } from './AiNotice';
import { dday } from '@/lib/ui';

// FR-CONT-04 유사 공모전 추천 + FR-CONT-05 추천 이유 표시
// 추천 이유에는 'AI 추천' 배지를 항상 붙인다 (NFR-ETHIC-01).

export default function ContestCard({ contest }) {
  const urgent = contest.dDay <= 7;

  return (
    <li className="card">
      <Link href={'/contests/' + contest.id} className="contest-link">
        <div className="contest-badges">
          <span className={urgent ? 'badge mono badge-late' : 'badge mono'}>
            {dday(contest.dDay)}
          </span>
          <span className="badge">{contest.field}</span>
          {contest.aiGenerated && <AiBadge />}
        </div>

        <h3 className="contest-title">{contest.title}</h3>
        <p className="dim tiny contest-host">
          {contest.host} · 마감 {contest.deadline}
        </p>

        {contest.reason && <p className="contest-reason">{contest.reason}</p>}
      </Link>
    </li>
  );
}
