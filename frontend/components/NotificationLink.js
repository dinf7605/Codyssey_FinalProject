'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { api, getToken } from '@/lib/api';

// FR-ALARM-01~04 머리글·사이드바의 알림 링크 — 안 읽은 알림 수를 함께 보여 준다.
// 화면을 옮길 때와 1분마다 다시 센다 (알림 워커가 1분마다 돈다). 비회원에게는 보이지 않는다.

const POLL_MS = 60 * 1000;

export default function NotificationLink({ position }) {
  const pathname = usePathname();
  const [state, setState] = useState({ token: null, unread: 0 });

  useEffect(() => {
    let alive = true;
    const token = getToken();
    if (!token) return undefined;

    async function load() {
      try {
        const rows = await api.notifications.list();
        if (alive && getToken() === token) setState({ token, unread: rows.filter((r) => !r.is_read).length });
      } catch {
        // 못 세면 숫자 없이 링크만 둔다
        if (alive) setState({ token, unread: 0 });
      }
    }

    load();
    const timer = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [pathname]);

  if (!state.token || state.token !== getToken()) return null;

  const selected = pathname === '/notifications';
  const label = state.unread ? `알림 ${state.unread}건 안 읽음` : '알림';
  const count = state.unread > 99 ? '99+' : state.unread;

  if (position === 'side') {
    return (
      <Link href="/notifications" className={`sidenav-item${selected ? ' sidenav-active' : ''}`}
        aria-current={selected ? 'page' : undefined} aria-label={label}>
        <BellIcon strokeWidth={selected ? 2 : 1.6} />
        <span>알림</span>
        {state.unread > 0 && <span className="noti-count mono">{count}</span>}
      </Link>
    );
  }
  return (
    <Link href="/notifications" className="noti-link tiny muted" aria-label={label}>
      <BellIcon strokeWidth={1.8} />
      {state.unread > 0 && <span className="noti-count mono">{count}</span>}
    </Link>
  );
}

function BellIcon({ strokeWidth }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}
