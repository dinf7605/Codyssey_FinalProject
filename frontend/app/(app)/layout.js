import TopBar from '@/components/TopBar';
import BottomNav from '@/components/BottomNav';
import { levelOf } from '@/lib/growth';
import { user } from '@/lib/mock';

// 로그인 후 화면들의 공통 껍데기.
// 온보딩과 랜딩은 집중이 필요한 흐름이라 이 레이아웃을 쓰지 않는다.
export default function AppLayout({ children }) {
  const { name } = levelOf(user.totalMinutes);

  return (
    <>
      <TopBar nickname={user.nickname} streakDays={user.streakDays} levelName={name} />
      <main className="shell page">{children}</main>
      <BottomNav />
    </>
  );
}
