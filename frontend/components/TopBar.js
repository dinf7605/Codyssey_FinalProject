import Link from 'next/link';

// FR-MAIN-01 로고 / FR-MAIN-02 로그인 상태별 메뉴
export default function TopBar({ nickname, streakDays, levelName }) {
  return (
    <header className="topbar">
      <div className="shell topbar-in">
        <Link href="/dashboard" className="brand">StudyPace</Link>
        <div className="topbar-right">
          {streakDays > 0 && <span className="tag tag-accent">{streakDays}일 연속</span>}
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
