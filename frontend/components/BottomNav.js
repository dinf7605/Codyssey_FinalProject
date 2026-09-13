'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { IconToday, IconSchedule, IconContest, IconMe } from './Icon';

// 모바일이 주력이므로 하단 탭이 기본 내비게이션이다.
// 탭은 4개까지만 둔다 — 5개를 넘으면 한 손 조작에서 오탭이 늘어난다.
const TABS = [
  { href: '/dashboard', label: '오늘', Icon: IconToday },
  { href: '/schedule', label: '일정', Icon: IconSchedule },
  { href: '/contests', label: '공모전', Icon: IconContest },
  { href: '/mypage', label: '내정보', Icon: IconMe },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {TABS.map(({ href, label, Icon }) => {
        const active = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={active ? 'tab tab-active' : 'tab'}
            aria-current={active ? 'page' : undefined}
          >
            <Icon strokeWidth={active ? 2 : 1.6} />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
