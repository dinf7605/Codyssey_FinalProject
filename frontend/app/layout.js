import localFont from 'next/font/local';
import './globals.css';
import { densityForLevel } from '@/lib/ui';

const namsan = localFont({
  src: [
    { path: './fonts/SeoulNamsanL.ttf', weight: '300', style: 'normal' },
    { path: './fonts/SeoulNamsanM.ttf', weight: '400 500', style: 'normal' },
    { path: './fonts/SeoulNamsanB.ttf', weight: '600 700', style: 'normal' },
    { path: './fonts/SeoulNamsanEB.ttf', weight: '800 900', style: 'normal' },
  ],
  variable: '--font-namsan',
  display: 'swap',
});

export const metadata = {
  title: 'StudyPace — 학습 목표 기반 맞춤 일정 플래너',
  description:
    '목표만 정하면 오늘 무엇을 공부할지까지 자동으로 쪼개 줍니다. 밀리면 매일 밤 다시 짜 드립니다.',
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5, // 확대를 막지 않는다 — 접근성 (NFR-A11Y-01)
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#F4F4F1' },
    { media: '(prefers-color-scheme: dark)', color: '#14151A' },
  ],
};

export default function RootLayout({ children }) {
  // FR-UI-01 / FR-UI-02 — 누적 학습시간이 레벨을, 레벨이 테마와 밀도를 정한다.
  // 서버는 사용자의 기록을 모르므로 레벨 1로 그리고, 로그인한 화면에서
  // components/AdaptiveTheme.js 가 실제 레벨로 바꾼다.
  const level = 1;
  const density = densityForLevel(level);

  return (
    <html
      lang="ko"
      data-level={level}
      data-density={density}
      className={namsan.variable}
    >
      <body>
        {children}
        <footer className="font-credit">
          서체: <a href="https://www.seoul.go.kr/seoul/font.do" target="_blank" rel="noreferrer">서울특별시 서울남산체</a>
        </footer>
      </body>
    </html>
  );
}
