'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { api, getToken } from '@/lib/api';
import SideNav from '@/components/SideNav';
import TopBar from '@/components/TopBar';

const AccountContext = createContext(null);

export function CurrentAccountProvider({ children }) {
  const [account, setAccount] = useState(null);
  const pathname = usePathname();

  useEffect(() => {
    let active = true;
    const token = getToken();

    async function load() {
      try {
        const profile = token ? await api.settings.profile() : null;
        if (active && getToken() === token) setAccount(profile);
      } catch {
        if (active) setAccount(null);
      }
    }

    load();
    return () => { active = false; };
  }, [pathname]);

  return (
    <AccountContext.Provider value={account}>
      {children}
    </AccountContext.Provider>
  );
}

// 로그인한 계정의 프로필 (닉네임 등). 비회원이거나 아직 못 읽었으면 null
export function useAccount() {
  return useContext(AccountContext);
}

export function AccountName() {
  const account = useContext(AccountContext);
  return account?.nickname ? `${account.nickname}님` : '내 계정';
}

export function AccountNavigation({ position }) {
  const account = useContext(AccountContext);
  const Navigation = position === 'side' ? SideNav : TopBar;
  return <Navigation nickname={account?.nickname} />;
}
