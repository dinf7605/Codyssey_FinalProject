'use client';

import { createContext, useContext, useEffect, useState, useSyncExternalStore } from 'react';
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

function subscribeToken(onChange) {
  window.addEventListener('storage', onChange);
  return () => window.removeEventListener('storage', onChange);
}
const readSignedIn = () => Boolean(getToken());
const readSignedInOnServer = () => false;

export function AccountNavigation({ position }) {
  const account = useContext(AccountContext);
  const signedIn = useSyncExternalStore(subscribeToken, readSignedIn, readSignedInOnServer);
  const Navigation = position === 'side' ? SideNav : TopBar;
  // 로그인했는데 닉네임이 없거나 프로필을 못 읽었어도 '로그인' 버튼을 띄우지 않는다
  const name = account?.nickname ? `${account.nickname}님` : signedIn ? '내 계정' : null;
  return <Navigation name={name} />;
}
