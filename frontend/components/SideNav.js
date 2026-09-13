'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { NAV_TABS } from '@/lib/nav';
import { ICONS } from './Icon';
import { dday } from '@/lib/ui';

// PC 전용 왼쪽 내비게이션.
// 넓은 화면에서 가로 탭 한 줄만 띄우면 남는 공간이 그대로 비어 보인다.
// 모바일에서는 CSS로 숨기고 BottomNav가 대신한다.

export default function SideNav({ nickname, levelName, streakDays, goal }) {
  const pathname = usePathname();

  return (
    <aside className="sidenav">
      <div className="sidenav-in">
        <Link href="/dashboard" className="brand sidenav-brand">StudyPace</Link>

        <nav aria-label="주요 메뉴" className="sidenav-list">
          {NAV_TABS.map(({ href, label, icon }) => {
            const Icon = ICONS[icon];
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={active ? 'sidenav-item sidenav-active' : 'sidenav-item'}
                aria-current={active ? 'page' : undefined}
              >
                <Icon width={18} height={18} strokeWidth={active ? 2 : 1.6} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        {nickname && (
          <Link href="/mypage" className="sidenav-user">
            {goal && (
              <span className="sidenav-goal">
                <span className="sidenav-goal-title">{goal.title}</span>
                <span className="sidenav-dday mono">{dday(goal.dDay)}</span>
              </span>
            )}
            <span className="sidenav-user-name">{nickname}님</span>
            <span className="micro dim">
              {levelName}
              {streakDays > 0 ? ' · ' + streakDays + '일 연속' : ''}
            </span>
          </Link>
        )}
      </div>
    </aside>
  );
}
