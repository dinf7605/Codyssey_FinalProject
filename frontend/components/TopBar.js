import Link from 'next/link';
import { dday } from '@/lib/ui';

// FR-MAIN-01 로고 / FR-MAIN-02 로그인 상태별 메뉴
// PC에서는 사이드바가 브랜드와 계정을 맡으므로 이 막대 자체를 숨긴다.

export default function TopBar({ nickname, streakDays, levelName, goal }) {
  return (
    <header className="topbar">
      <div className="shell topbar-in">
        <Link href="/dashboard" className="brand">StudyPace</Link>
        <div className="topbar-right">
          {goal && <span className="tag tag-accent mono">{dday(goal.dDay)}</span>}
          {nickname ? (
            <Link href="/mypage" className="tiny muted">
              {nickname}님{levelName ? ' · ' + levelName : ''}
            </Link>
          ) : (
            <Link href="/login" className="tiny" style={{ fontWeight: 600 }}>로그인</Link>
          )}
        </div>
      </div>
    </header>
  );
}
