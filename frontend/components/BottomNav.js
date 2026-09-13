'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { NAV_TABS } from '@/lib/nav';
import { ICONS } from './Icon';

// 모바일 전용 하단 탭. PC에서는 SideNav가 대신한다 (CSS에서 숨김).
// 탭은 4개까지만 둔다 — 5개를 넘으면 한 손 조작에서 오탭이 늘어난다.

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {NAV_TABS.map(({ href, label, icon }) => {
        const Icon = ICONS[icon];
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
