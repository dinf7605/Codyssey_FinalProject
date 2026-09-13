'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

// 모바일이 주력이므로 하단 탭이 기본 내비게이션이다.
// 탭은 4개까지만 둔다 — 5개를 넘으면 한 손 조작에서 오탭이 늘어난다.
const TABS = [
  { href: '/dashboard', label: '오늘', icon: '◉' },
  { href: '/schedule', label: '일정', icon: '▦' },
  { href: '/contests', label: '공모전', icon: '◈' },
  { href: '/mypage', label: '내정보', icon: '☰' },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {TABS.map((tab) => {
        const active = pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={active ? 'tab tab-active' : 'tab'}
            aria-current={active ? 'page' : undefined}
          >
            <span className="tab-icon" aria-hidden="true">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
