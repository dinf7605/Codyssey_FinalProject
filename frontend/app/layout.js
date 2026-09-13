import './globals.css';
import { densityForLevel } from '@/lib/ui';
import { user } from '@/lib/mock';

export const metadata = {
  title: 'StudyPace — 학습 목표 기반 맞춤 일정 플래너',
  description:
    '목표만 정하면 오늘 무엇을 공부할지까지 자동으로 쪼개 줍니다. 밀리면 매일 밤 다시 짜 드립니다.',
};

// 모바일이 주력이므로 뷰포트를 명시한다.
// viewportFit=cover + CSS의 env(safe-area-inset-*)으로 아이폰 노치·홈바를 피한다.
export const viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5, // 확대를 막지 않는다 — 접근성 (NFR-A11Y-01)
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#F1F3F6' },
    { media: '(prefers-color-scheme: dark)', color: '#0F1318' },
  ],
};

export default function RootLayout({ children }) {
  // FR-UI-01 / FR-UI-02 — 레벨에 따라 테마와 정보 밀도가 달라진다.
  // 백엔드가 붙으면 user 값을 세션에서 읽어 온다.
  const density = densityForLevel(user.level);

  return (
    <html lang="ko" data-level={user.level} data-density={density}>
      <body>{children}</body>
    </html>
  );
}
