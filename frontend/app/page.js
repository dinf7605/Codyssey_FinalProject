import Link from 'next/link';
import { AiNotice } from '@/components/AiNotice';

// 비회원이 처음 보는 화면.
// 기능을 나열하는 대신 '받게 될 일정'을 그대로 보여주고,
// 사람들이 실제로 하는 질문 순서로 읽히게 한다.

const SAMPLE = [
  { time: '09:00', title: '소프트웨어 설계', scope: '2단원 요구사항 확인 · 60분' },
  { time: '14:00', title: '데이터베이스 구축', scope: '3단원 물리 데이터베이스 · 90분' },
  { time: '20:00', title: '기출 풀이', scope: '2023년 2회차 1~40번 · 60분' },
];

const QA = [
  {
    q: '계획을 세워도 왜 무너질까요',
    a: '"하루 2시간"까지는 정해도, 오늘 무엇을 볼지에서 막히기 때문입니다. 그 판단을 매일 스스로 해야 하면 오래 가지 못합니다.',
  },
  {
    q: '그래서 무엇이 다른가요',
    a: '목표를 30~120분짜리 학습 단위로 쪼개고, 비어 있는 시간에 순서를 지켜 배치합니다. 아침에 열면 오늘 볼 범위가 이미 정해져 있습니다.',
  },
  {
    q: '하루 밀리면요',
    a: '매일 새벽에 못 한 분량을 남은 기간에 다시 배치합니다. 계획을 처음부터 다시 짤 필요가 없습니다.',
  },
  {
    q: '기한 안에 되는지는 어떻게 아나요',
    a: '표준 학습시간과 낼 수 있는 시간을 대조해 최소 몇 주가 필요한지 먼저 계산합니다. 무리한 목표는 추천 단계에서 걸러집니다.',
  },
];

export default function LandingPage() {
  return (
    <div className="landing">
    <main className="shell page" style={{ paddingBottom: 'var(--gap-6)' }}>
      <div className="landing-top">
      <section className="hero">
        <h1 className="title">
          이 자격증,
          <br />
          기한 안에 끝낼 수 있을까?
        </h1>
        <p className="hero-sub">
          목표만 정하면 오늘 저녁 7시에 무엇을 공부할지까지 쪼개 드립니다.
          하루 밀려도 계획을 다시 짤 필요가 없습니다.
        </p>

        <div className="hero-cta">
          <Link href="/onboarding" className="btn btn-primary">내게 맞는 목표 찾기</Link>
          <Link href="/contests" className="btn">공모전 먼저 둘러보기</Link>
        </div>
        <p className="hint hero-hint" style={{ marginTop: 10, textAlign: 'center' }}>
          가입 없이 목표 추천까지 이용할 수 있습니다
        </p>
      </section>

      <section className="sec">
        <div className="paper">
          <div className="paper-head">
            <span className="tiny" style={{ fontWeight: 600 }}>받게 되는 하루</span>
            <span className="pill">예시</span>
          </div>
          <div className="paper-body">
            <ol className="tl">
              {SAMPLE.map((row) => (
                <li className="tl-item" key={row.time}>
                  <span className="tl-time">{row.time}</span>
                  <span className="tl-dot" />
                  <div className="tl-body">
                    <span className="tl-title">{row.title}</span>
                    <span className="tl-sub">{row.scope}</span>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
        <AiNotice>
          화면의 일정은 예시입니다. 실제 일정은 입력하신 가용 시간과 목표에 따라 AI가 생성하며, 부정확할 수 있습니다.
        </AiNotice>
      </section>
      </div>

      <section className="qa">
        {QA.map((item) => (
          <div className="qa-item" key={item.q}>
            <h2 className="qa-q">{item.q}</h2>
            <p className="qa-a">{item.a}</p>
          </div>
        ))}
      </section>

      <section className="sec">
        <div className="sec-head">
          <h2 className="h-sec">쓸수록 채워집니다</h2>
        </div>
        <p className="lead">
          처음에는 오늘 할 일만 보입니다. 기록이 쌓이면 연속 학습일, 진도 신호등,
          학습 잔디, 시간대별 패턴이 차례로 열립니다.
          빈 그래프를 먼저 보여주지 않는 이유입니다.
        </p>
      </section>

      <footer className="landing-foot" style={{ borderTop: '1px solid var(--rule)', paddingTop: 'var(--gap-4)', display: 'flex', flexDirection: 'column', gap: 9 }}>
        <div style={{ display: 'flex', gap: 18, fontSize: 13 }}>
          <Link href="/login">로그인</Link>
          <Link href="/signup">회원가입</Link>
        </div>
        <p className="dim micro">
          캘린더는 빈 시간대만 읽으며 일정 제목과 참석자는 저장하지 않습니다.
        </p>
      </footer>
    </main>
    </div>
  );
}
