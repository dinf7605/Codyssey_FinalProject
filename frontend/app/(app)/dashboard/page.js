import Link from 'next/link';
import PaceSignal from '@/components/PaceSignal';
import BlockCard from '@/components/BlockCard';
import ContestCard from '@/components/ContestCard';
import SectionTitle from '@/components/SectionTitle';
import EmptyState from '@/components/EmptyState';
import { AiNotice } from '@/components/AiNotice';
import { goal, pace, todayBlocks, contests, user } from '@/lib/mock';

// FR-MAIN-03 오늘의 학습 블록 / FR-MAIN-04 목표 진행률
// FR-MAIN-05 추천 공모전 배너 / FR-PACE-04 진도 신호등

export default function DashboardPage() {
  const remaining = todayBlocks.filter((b) => !b.done).length;
  const weekly = contests.slice(0, 2);

  return (
    <>
      <header className="stack" style={{ gap: 4 }}>
        <h1 style={{ fontSize: 20 }}>
          {user.nickname}님, {remaining > 0 ? remaining + '개 남았어요' : '오늘 할 일을 다 마쳤어요'}
        </h1>
        <p className="muted tiny">오늘의 학습</p>
      </header>

      <PaceSignal goal={goal} pace={pace} />

      <section>
        <SectionTitle moreHref="/schedule">오늘의 학습</SectionTitle>

        {todayBlocks.length === 0 ? (
          <EmptyState
            title="오늘은 휴식일입니다"
            description="주 1일은 휴식일로 확보합니다. 지금 일정을 다시 만들 수도 있어요."
            action={<button className="btn btn-sm">일정 다시 만들기</button>}
          />
        ) : (
          <ul className="list">
            {todayBlocks.map((block) => (
              <BlockCard key={block.id} block={block} />
            ))}
          </ul>
        )}

        <Link href="/study" className="btn btn-primary" style={{ marginTop: 'var(--gap-3)' }}>
          학습 시작하기
        </Link>
      </section>

      <section>
        <SectionTitle moreHref="/contests">이번 주 추천 공모전</SectionTitle>
        {weekly.length === 0 ? (
          <EmptyState title="이번 주에는 조건에 맞는 공모전을 찾지 못했습니다" />
        ) : (
          <>
            <ul className="list">
              {weekly.map((c) => (
                <ContestCard key={c.id} contest={c} />
              ))}
            </ul>
            <div style={{ marginTop: 'var(--gap-3)' }}>
              <AiNotice />
            </div>
          </>
        )}
      </section>
    </>
  );
}
