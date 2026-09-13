'use client';

import { useState } from 'react';
import Link from 'next/link';
import DayTimeline from '@/components/DayTimeline';
import StudyGrass from '@/components/StudyGrass';
import PaceSignal from '@/components/PaceSignal';
import ContestCard from '@/components/ContestCard';
import SectionTitle from '@/components/SectionTitle';
import EmptyState from '@/components/EmptyState';
import GrowthPreview from '@/components/GrowthPreview';
import { AiNotice } from '@/components/AiNotice';
import { levelOf, isOpen, nextUnlock, nextFromLevel } from '@/lib/growth';
import { goal, pace, todayBlocks, contests, user, studyHistory, hourPattern } from '@/lib/mock';

// FR-MAIN-03~05 / FR-PACE-04 / FR-UI-01 / FR-UI-02
//
// 화면은 학습량에 따라 열린다 (lib/growth.js).
// 기록이 없는 사람에게 빈 그래프를 보여주는 대신 오늘 할 일만 두고 시작한다.

export default function DashboardPage() {
  const actual = levelOf(user.totalMinutes).level;
  const [level, setLevel] = useState(actual);

  const remaining = todayBlocks.filter((b) => !b.done).length;
  // 미리보기로 레벨을 바꿔 본 상태에서는 시간 계산 대신 그 레벨의 다음 단계를 보여준다
  const next = level === actual ? nextUnlock(user.totalMinutes) : nextFromLevel(level);
  const totalHours = Math.round(user.totalMinutes / 60);
  const weekMinutes = studyHistory.slice(-7).reduce((s, d) => s + d.minutes, 0);
  const peak = Math.max(...hourPattern.map((h) => h.value));

  return (
    <>
      <header className="stack" style={{ gap: 6 }}>
        <p className="tiny dim">9월 14일 일요일</p>
        <h1 className="title">
          {remaining > 0 ? '오늘 ' + remaining + '개 남았어요' : '오늘 할 일을 다 마쳤어요'}
        </h1>
      </header>

      <GrowthPreview level={level} onChange={setLevel} />

      <div className="cols">
        <div className="col col-main">
      {/* 오늘 — 레벨과 무관하게 항상 보인다 */}
      <section className="sec">
        <SectionTitle moreHref="/schedule">오늘의 학습</SectionTitle>
        {todayBlocks.length === 0 ? (
          <EmptyState
            title="오늘은 휴식일입니다"
            description="주 1일은 휴식일로 확보합니다."
            action={<button className="btn btn-sm">일정 다시 만들기</button>}
          />
        ) : (
          <DayTimeline blocks={todayBlocks} />
        )}
        <Link href="/study" className="btn btn-primary">학습 시작하기</Link>
      </section>

      {/* 레벨 2 — 기록 요약 */}
      {isOpen(level, 'streak') && (
        <section className="sec">
          <SectionTitle>기록</SectionTitle>
          <div className="stats">
            <div className="stat">
              <span className="stat-label">연속</span>
              <span className="stat-value">{user.streakDays}<small>일</small></span>
            </div>
            <div className="stat">
              <span className="stat-label">이번 주</span>
              <span className="stat-value">{Math.round(weekMinutes / 60)}<small>시간</small></span>
            </div>
            <div className="stat">
              <span className="stat-label">누적</span>
              <span className="stat-value">{totalHours}<small>시간</small></span>
            </div>
          </div>
        </section>
      )}

      {/* 레벨 3 — 진도 신호등 */}
      {isOpen(level, 'pace') && <PaceSignal goal={goal} pace={pace} />}
        </div>

        {/* PC에서는 기록 계열을 오른쪽 기둥으로 보낸다.
            모바일에서는 그대로 아래로 이어진다 (.cols가 세로 배치) */}
        <div className="col col-side">

      {/* 레벨 4 — 학습 잔디 */}
      {isOpen(level, 'grass') && (
        <section className="sec">
          <SectionTitle>학습 기록</SectionTitle>
          <StudyGrass history={studyHistory} weeks={16} />
        </section>
      )}

      {/* 레벨 4 — 시간대 패턴 */}
      {isOpen(level, 'pattern') && (
        <section className="sec">
          <SectionTitle>언제 잘 되나요</SectionTitle>
          <div>
            <div className="pattern">
              {hourPattern.map((h) => (
                <div
                  key={h.label}
                  className={h.value === peak ? 'pattern-bar peak' : 'pattern-bar'}
                  style={{ height: Math.round((h.value / peak) * 100) + '%' }}
                  title={h.label + ' · ' + h.value + '회'}
                />
              ))}
            </div>
            <div className="pattern-labels">
              {hourPattern.map((h) => (
                <span key={h.label}>{h.label}</span>
              ))}
            </div>
          </div>
          <p className="hint">21시 전후에 가장 자주 학습했습니다. 일정도 이 시간대를 우선 배정합니다.</p>
        </section>
      )}

      {/* 레벨 5 — 습관 분석 */}
      {isOpen(level, 'insight') && (
        <section className="sec">
          <SectionTitle>학습 습관</SectionTitle>
          <div className="rows">
            <div className="row">
              <div className="row-main">
                <b>예상보다 오래 걸리는 편</b>
                <span>완료한 블록이 평균 18퍼센트 더 걸렸습니다. 일정에 반영해 두었습니다.</span>
              </div>
            </div>
            <div className="row">
              <div className="row-main">
                <b>주말에 몰아서 하는 편</b>
                <span>토요일 학습량이 평일 평균의 1.7배입니다.</span>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 레벨 3 — 공모전 추천 */}
      {isOpen(level, 'contests') && (
        <section className="sec">
          <SectionTitle moreHref="/contests">이번 주 추천 공모전</SectionTitle>
          {contests.length === 0 ? (
            <EmptyState title="이번 주에는 조건에 맞는 공모전을 찾지 못했습니다" />
          ) : (
            <>
              <ul className="list">
                {contests.slice(0, 2).map((c) => (
                  <ContestCard key={c.id} contest={c} />
                ))}
              </ul>
              <AiNotice />
            </>
          )}
        </section>
      )}

      {/* 다음에 무엇이 열리는지 알려준다 — 없으면 그냥 '기능이 없는 화면'이 된다 */}
      {next && level < 5 && (
        <div className="next-level">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span className="tiny" style={{ fontWeight: 600 }}>
              {next.remainingHours ? next.remainingHours + '시간 더 공부하면' : '다음 단계'}
            </span>
            <span className="micro dim mono">레벨 {next.level} · {next.name}</span>
          </div>
          <div className="bar">
            <div className="bar-fill" style={{ width: next.percent + '%' }} />
          </div>
          <p className="micro dim">{next.items.join(' · ')}이(가) 열립니다</p>
        </div>
      )}
        </div>
      </div>
    </>
  );
}
