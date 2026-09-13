import Link from 'next/link';

// FR-MAIN-01 로고 / FR-MAIN-02 로그인 상태별 메뉴
export default function TopBar({ title, nickname, streakDays }) {
  return (
    <header className="topbar">
      <div className="shell topbar-in">
        <Link href="/dashboard" className="brand">
          {title || 'StudyPace'}
        </Link>

        <div className="topbar-right">
          {streakDays > 0 && (
            <span className="badge badge-ok mono" title="연속 학습일">
              {streakDays}일 연속
            </span>
          )}
          {nickname ? (
            <Link href="/mypage" className="tiny muted">{nickname}님</Link>
          ) : (
            <Link href="/login" className="tiny strong accent-text">로그인</Link>
          )}
        </div>
      </div>
    </header>
  );
}
