import TopBar from '@/components/TopBar';
import SideNav from '@/components/SideNav';
import BottomNav from '@/components/BottomNav';
import { levelOf } from '@/lib/growth';
import { user } from '@/lib/mock';

// 로그인 후 화면들의 공통 껍데기.
//   모바일 — 상단 막대 + 하단 탭
//   PC     — 왼쪽 사이드바 (상단 막대·하단 탭은 CSS에서 숨김)
// 온보딩과 랜딩은 집중이 필요한 흐름이라 이 레이아웃을 쓰지 않는다.

export default function AppLayout({ children }) {
  const { name } = levelOf(user.totalMinutes);

  return (
    <div className="app">
      <SideNav nickname={user.nickname} levelName={name} streakDays={user.streakDays} />
      <div className="app-body">
        <TopBar nickname={user.nickname} streakDays={user.streakDays} levelName={name} />
        <main className="shell page">{children}</main>
      </div>
      <BottomNav />
    </div>
  );
}
