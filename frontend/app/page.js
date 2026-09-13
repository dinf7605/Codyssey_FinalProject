import Link from 'next/link';
import { AiNotice } from '@/components/AiNotice';

// 비회원이 처음 보는 화면.
// 설명만 늘어놓지 않고 '받게 될 일정'을 그대로 보여준다 —
// 이 서비스가 무엇을 해주는지 한 화면에서 이해되게 하는 것이 목적이다.

const SAMPLE = [
  { time: '09:00', title: '소프트웨어 설계', scope: '2단원 요구사항 확인 · 60분' },
  { time: '14:00', title: '데이터베이스 구축', scope: '3단원 물리 데이터베이스 · 90분' },
  { time: '20:00', title: '기출 풀이', scope: '2023년 2회차 1~40번 · 60분' },
];

const STEPS = [
  {
    title: '관심 분야와 낼 수 있는 시간을 알려주세요',
    desc: '요일별로 몇 시에 공부할 수 있는지만 고르면 됩니다. 구글 캘린더를 연동하면 빈 시간을 자동으로 찾습니다.',
  },
  {
    title: '기한 안에 가능한 목표만 추천합니다',
    desc: '표준 학습시간과 가용 시간을 대조해 실제로 끝낼 수 있는 자격증·공모전만 남깁니다.',
  },
  {
    title: '오늘 할 일까지 쪼개 드립니다',
    desc: '목표를 30~120분짜리 학습 단위로 나눠 빈 시간에 배치합니다. 밀리면 매일 밤 자동으로 다시 짭니다.',
  },
];

export default function LandingPage() {
  return (
    <main className="shell page" style={{ paddingBottom: 'var(--gap-6)' }}>
      <section className="hero">
        <span className="badge badge-accent">AI 학습 일정 플래너</span>
        <h1 style={{ marginTop: 'var(--gap-3)' }}>
          이 자격증,
          <br />
          기한 안에 끝낼 수 있을까?
        </h1>
        <p className="hero-sub">
          목표만 정하면 <b>오늘 저녁 7시에 무엇을 공부할지</b>까지 쪼개 드립니다.
          하루 밀려도 계획을 처음부터 다시 짤 필요가 없습니다.
        </p>

        <div className="hero-cta">
          <Link href="/onboarding" className="btn btn-primary">
            내게 맞는 목표 찾기
          </Link>
          <Link href="/contests" className="btn">
            공모전 먼저 둘러보기
          </Link>
        </div>
        <p className="hint" style={{ marginTop: 'var(--gap-2)', textAlign: 'center' }}>
          가입 없이 목표 추천까지 이용할 수 있습니다
        </p>
      </section>

      {/* 말로 설명하는 대신 결과물을 그대로 보여준다 */}
      <section>
        <div className="preview">
          <div className="preview-head">
            <span className="tiny strong">이런 일정을 받게 됩니다</span>
            <span className="badge mono">예시</span>
          </div>
          <div className="preview-body">
            {SAMPLE.map((row) => (
              <div className="preview-row" key={row.time}>
                <span className="preview-time mono">{row.time}</span>
                <span className="preview-what">
                  <b>{row.title}</b>
                  <span>{row.scope}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ marginTop: 'var(--gap-3)' }}>
          <AiNotice>
            화면의 일정은 예시입니다. 실제 일정은 입력하신 가용 시간과 목표에 따라 AI가 생성하며,
            부정확할 수 있습니다.
          </AiNotice>
        </div>
      </section>

      <section>
        <div className="section-title">
          <h2>어떻게 만들어지나요</h2>
        </div>
        <div className="steps">
          {STEPS.map((step, i) => (
            <div className="step" key={step.title}>
              <span className="step-no">{i + 1}</span>
              <div className="step-body">
                <b>{step.title}</b>
                <p>{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer
        style={{
          borderTop: '1px solid var(--rule)',
          paddingTop: 'var(--gap-4)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--gap-2)',
        }}
      >
        <div style={{ display: 'flex', gap: 'var(--gap-4)', fontSize: 13 }}>
          <Link href="/login" className="accent-text">로그인</Link>
          <Link href="/signup" className="accent-text">회원가입</Link>
        </div>
        <p className="dim tiny">
          캘린더는 빈 시간대만 읽으며 일정 제목과 참석자는 저장하지 않습니다.
        </p>
      </footer>
    </main>
  );
}
