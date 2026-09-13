import { Gowun_Batang, IBM_Plex_Sans_KR, IBM_Plex_Mono } from 'next/font/google';
import './globals.css';
import { levelOf } from '@/lib/growth';
import { densityForLevel } from '@/lib/ui';
import { user } from '@/lib/mock';

// next/font는 빌드 시점에 폰트를 가져와 같은 도메인에서 내려준다.
// 외부 스타일시트를 부르지 않아 첫 화면이 늦게 뜨거나 글자가 튀는 일이 없다.
const display = Gowun_Batang({
  subsets: ['latin'],
  weight: ['400', '700'],
  variable: '--font-display',
  display: 'swap',
});

const body = IBM_Plex_Sans_KR({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-body',
  display: 'swap',
});

const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono-src',
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
  const level = levelOf(user.totalMinutes).level;
  const density = densityForLevel(level);

  return (
    <html
      lang="ko"
      data-level={level}
      data-density={density}
      className={`${display.variable} ${body.variable} ${mono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
