import Link from 'next/link';
import Image from 'next/image';
import { AiBadge, AiNotice } from '@/components/AiNotice';
import styles from './home.module.css';

const steps = [
  ['01', '나에게 맞는 목표 찾기', '관심분야와 공부할 수 있는 시간을 바탕으로 시작할 목표를 찾아보세요.'],
  ['02', '실행할 수 있는 계획 만들기', 'AI가 목표를 작은 학습 단위로 나누고, 내 가용시간에 맞춰 배치합니다.'],
  ['03', '오늘의 공부를 기록하기', '타이머로 공부 시간을 남기고, 완료한 학습과 목표까지의 진도를 확인하세요.'],
];

export default function HomePage() {
  return (
    <div className={styles.home}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand}>StudyPace<span>내 속도로, 끝까지.</span></Link>
        <nav aria-label="시작 메뉴" className={styles.actions}>
          <Link href="/login" className="btn btn-quiet btn-sm">로그인</Link>
          <Link href="/signup" className="btn btn-sm">회원가입</Link>
        </nav>
      </header>
      <main>
        <section className={styles.hero} aria-labelledby="home-title">
          <div>
            <Image
              src="/learning-path-blue.png"
              alt=""
              width={2172}
              height={724}
              sizes="(max-width: 800px) 90vw, 480px"
              className={styles.heroArt}
            />
            <p className={styles.eyebrow}>목표에서 오늘의 공부까지</p>
            <h1 id="home-title" className={styles.title}>막연한 목표를<br />오늘 할 일로.</h1>
            <p className={styles.description}>무엇부터 시작할지 고민될 때,<br />내 시간에 맞는 학습 계획을 만들어 보세요.<br />StudyPace가 매일의 공부를 이어갈 수 있게 도와드립니다.</p>
            <div className={styles.actions}>
              <Link href="/onboarding" className="btn btn-primary">내게 맞는 목표 찾기 →</Link>
              <Link href="/dashboard" className="btn btn-yellow">내 학습 보기</Link>
            </div>
            <p className={styles.hint}>목표 탐색과 계획 생성은 로그인 없이 시작할 수 있어요.<br />계획 저장과 학습 기록에는 로그인이 필요합니다.</p>
          </div>
          <aside className={styles.preview} aria-label="학습 일정 예시">
            <div className={styles.animatedIllustration}>
              <video
                className={styles.studyVideo}
                poster="/study-blue.png"
                autoPlay
                muted
                loop
                playsInline
                controls
                preload="metadata"
                aria-label="학습 목표와 오늘의 공부를 소개하는 영상"
              >
                <source src="/study-blue.mp4" type="video/mp4" />
                영상을 재생할 수 없습니다.
              </video>
            </div>
            <div className={styles.previewHead}><span>이렇게 시작해요</span><span className="pill">화면 예시</span></div>
            <h2>조금씩, 꾸준히 쌓이는 하루</h2>
            <p className={styles.hint}>예시 목표 · 데이터 분석 기초</p>
            <ol className={styles.timeline}>
              {[
                ['19:00', '데이터의 종류 이해하기', '개념 읽기와 핵심 내용 정리 · 30분'],
                ['19:30', '배운 내용 직접 써 보기', '간단한 표로 연습하기 · 30분'],
                ['20:00', '오늘의 학습 마무리', '완료 표시와 학습 메모 남기기'],
              ].map(([time, title, detail]) => <li key={time}><span className={styles.time}>{time}</span><div><b>{title}</b><p>{detail}</p></div></li>)}
            </ol>
            <div className={styles.previewFoot}><AiBadge /><span>목표와 가용시간에 따라 계획이 달라집니다.</span></div>
            <AiNotice>AI가 생성한 학습 계획은 부정확할 수 있습니다. 내용과 예상 시간을 확인하고 조정해 주세요.</AiNotice>
          </aside>
        </section>
        <section className={styles.steps} aria-labelledby="steps-title">
          <p className={styles.eyebrow}>HOW IT WORKS</p>
          <h2 id="steps-title">시작은 가볍게, 기록은 차곡차곡.</h2>
          <ol className={styles.stepGrid}>{steps.map(([number, title, description]) => (
            <li key={number}><span className={styles.number}>{number}</span><h3>{title}</h3><p>{description}</p></li>
          ))}</ol>
        </section>
        <section className={styles.explore} aria-labelledby="explore-title">
          <div><h2 id="explore-title">배운 것을 펼칠 기회도 찾아보세요.</h2><p>공모전 공고와 준비 기간을 확인하며 다음 목표를 생각해 볼 수 있어요.</p></div>
          <Link href="/contests" className="btn btn-yellow">공모전 둘러보기 →</Link>
        </section>
      </main>
      <footer className={styles.footer}><span>StudyPace · 내 속도로, 끝까지.</span><Link href="/onboarding">목표 찾기부터 시작하기 →</Link></footer>
    </div>
  );
}
