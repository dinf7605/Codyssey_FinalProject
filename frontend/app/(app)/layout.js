import { CurrentAccountProvider, AccountNavigation } from '@/components/CurrentAccount';
import AdaptiveTheme from '@/components/AdaptiveTheme';

import BottomNav from '@/components/BottomNav';
import ReconsentGate from '@/components/ReconsentGate';



// 로그인 후 화면들의 공통 껍데기.
//   모바일 — 상단 막대 + 하단 탭
//   PC     — 왼쪽 사이드바 (상단 막대·하단 탭은 CSS에서 숨김)
// 온보딩과 랜딩은 집중이 필요한 흐름이라 이 레이아웃을 쓰지 않는다.
// ReconsentGate — AI 이용 고지 문구가 바뀌었으면 다시 동의를 받는다 (FR-JOIN-03).

export default function AppLayout({ children }) {


  return (
    <CurrentAccountProvider>
    <AdaptiveTheme />
    <ReconsentGate />
    <div className="app">
      <AccountNavigation position="side" />
      <div className="app-body">
        <AccountNavigation position="top" />
        <main className="shell page">{children}</main>
      </div>
      <BottomNav />
    </div>
    </CurrentAccountProvider>
  );
}
