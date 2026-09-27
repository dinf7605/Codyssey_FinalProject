'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { api, getToken } from '@/lib/api';

export default function AdminNavigationLink({ position }) {
  const pathname = usePathname();
  const [access, setAccess] = useState(null);

  useEffect(() => {
    let active = true;
    const token = getToken();

    async function checkAccess() {
      let allowed = false;
      try {
        if (token) {
          const result = await api.admin.me();
          allowed = result?.is_admin === true;
        }
      } catch {
        // 권한 확인 실패 시 관리자 메뉴를 숨긴다.
        allowed = false;
      }

      if (active && getToken() === token) {
        setAccess({ pathname, token, allowed });
      }
    }

    checkAccess();
    return () => { active = false; };
  }, [pathname]);

  if (
    !access?.allowed ||
    access.pathname !== pathname ||
    access.token !== getToken()
  ) {
    return null;
  }

  const selected = pathname === '/admin' || pathname.startsWith('/admin/');
  const className = position === 'side'
    ? `sidenav-item${selected ? ' sidenav-active' : ''}`
    : 'tiny muted';

  return (
    <Link
      href="/admin"
      className={className}
      aria-current={selected ? 'page' : undefined}
    >
      {position === 'side' && (
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={selected ? 2 : 1.6}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      )}
      <span>관리자</span>
    </Link>
  );
}