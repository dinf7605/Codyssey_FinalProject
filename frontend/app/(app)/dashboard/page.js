'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import ProfileSummary from '@/components/ProfileSummary';
import DayTimeline from '@/components/DayTimeline';
import StudyGrass from '@/components/StudyGrass';
import PaceSignal from '@/components/PaceSignal';
import DeadlineContests from '@/components/DeadlineContests';
import SectionTitle from '@/components/SectionTitle';
import EmptyState from '@/components/EmptyState';
import { useAccount } from '@/components/CurrentAccount';
import { api } from '@/lib/api';
import { isOpen, nextUnlock } from '@/lib/growth';
import { goalView, milestones, paceOf } from '@/lib/pace';
import { dayKey, hhmm, kstToday, weekdayMon, WEEKDAY_MON } from '@/lib/planView';
import { subjectParticle } from '@/lib/ui';
import { usePlan } from '@/lib/usePlan';
import { useStats } from '@/lib/useStats';

// FR-MAIN-03~05 / FR-PACE-04 / FR-UI-01 / FR-UI-02
//
// 화면은 학습량에 따라 열린다 (lib/growth.js). 레벨은 저장된 학습 기록(/study/stats)으로만 정해진다.
// 기록이 없는 사람에게 빈 그래프를 보여주는 대신 오늘 할 일만 두고 시작한다.
// 모든 값은 실제 계획(/plan/active)·기록(/study/stats)·학습 메모리(/memories)에서 온다.

function todayLabel(today) {
  return `${Number(today.slice(5, 7))}월 ${Number(today.slice(8, 10))}일 ${WEEKDAY_MON[weekdayMon(today)]}요일`;
}

// FR-MEM-01 의 근거 있는 학습 메모리 — 레벨 5 '학습 습관'에 쓴다. 없으면 빈 목록
function useHabitMemories(enabled) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    api.memories.list().then(
      (data) => alive && setRows(Array.isArray(data) ? data : []),
      () => alive && setRows([]),
    );
    return () => {
      alive = false;
    };
  }, [enabled]);
  return rows;
}

function habitLines(rows) {
  const by = Object.fromEntries(rows.map((r) => [r.memory_type, r.value || {}]));
  const lines = [];
  if (by.effort_deviation && typeof by.effort_deviation.percent === 'number') {
    const p = by.effort_deviation.percent;
    lines.push({
      title: p > 0 ? '예상보다 오래 걸리는 편' : p < 0 ? '예상보다 빨리 끝내는 편' : '예상한 시간에 맞추는 편',
      detail: `블록이 예상보다 평균 ${p > 0 ? '+' : ''}${p}% 걸렸습니다 (최근 4주 ${by.effort_deviation.session_count}회 기준).`,
    });
  }
  if (by.preferred_study_time?.band) {
    lines.push({
      title: `${by.preferred_study_time.band}에 가장 많이 공부하는 편`,
      detail: `최근 4주 학습 ${by.preferred_study_time.session_count}회의 시작 시간과 학습량 기준입니다.`,
    });
  }
  if (by.four_week_completion_rate && typeof by.four_week_completion_rate.percent === 'number') {
    const c = by.four_week_completion_rate;
    lines.push({
      title: `최근 4주 완료율 ${c.percent}%`,
      detail: `계획한 블록 ${c.planned}개 중 ${c.completed}개를 끝냈습니다.`,
    });
  }
  return lines;
}

export default function DashboardPage() {
  const today = kstToday();
  const plan = usePlan();
  const stats = useStats();
  const account = useAccount();
  const signedIn = stats.status !== 'anon' && plan.status !== 'anon';
  const habits = habitLines(useHabitMemories(stats.status === 'ready' && (stats.data?.level ?? 1) >= 5));

  const header = (title) => (
    <header className="stack" style={{ gap: 6 }}>
      <p className="tiny dim">{todayLabel(today)}</p>
      <h1 className="title">{title}</h1>
    </header>
  );

  // 비회원 — 오늘 할 일·진도는 로그인해야 생긴다. 공개 공모전 목록은 그대로 보여준다
  if (!signedIn) {
    return (
      <>
        {header('오늘의 학습')}
        <EmptyState
          title="로그인하면 오늘 할 일과 진도가 보여요"
          description="목표를 정하면 공부 단위로 나눠 빈 시간에 놓아 드립니다. 목표 찾기는 로그인 없이도 됩니다."
          action={
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
              <Link className="btn btn-primary btn-sm" href="/login?next=/dashboard">로그인</Link>
              <Link className="btn btn-sm" href="/onboarding">내게 맞는 목표 찾기</Link>
            </div>
          }
        />
        <section className="sec">
          <SectionTitle moreHref="/contests">공모전 목록</SectionTitle>
          <DeadlineContests />
        </section>
      </>
    );
  }

  if (plan.status === 'loading' || stats.status === 'loading') {
    return (
      <>
        {header('오늘의 학습')}
        <p className="hint" role="status">불러오는 중…</p>
      </>
    );
  }

  if (plan.status === 'error' || stats.status === 'error') {
    return (
      <>
        {header('오늘의 학습')}
        <EmptyState
          title="학습 정보를 불러오지 못했어요"
          description={plan.error || stats.error || '잠시 뒤 다시 시도해 주세요.'}
          action={<button type="button" className="btn btn-sm" onClick={() => { plan.reload(); stats.reload(); }}>다시 시도</button>}
        />
      </>
    );
  }

  const s = stats.data;
  const level = s.level;
  const next = nextUnlock(s.total_minutes);
  const user = { nickname: account?.nickname || null, totalMinutes: s.total_minutes, streakDays: s.streak_days };

  // 계획을 아직 확정하지 않았다 — 기록 요약은 보여주되 오늘 할 일 대신 계획 만들기로 안내
  const hasPlan = plan.status === 'ready' && plan.plans.length > 0;
  const plans = hasPlan ? [...plan.plans].sort((a, b) => a.deadline.localeCompare(b.deadline)) : [];
  const primary = plans[0];

  const todayBlocks = plan.blocks
    .filter((b) => dayKey(b.start) === today)
    .sort((a, b) => a.start.localeCompare(b.start))
    .map((b) => ({
      id: b.id,
      start: hhmm(b.start),
      subject: b.title,
      scope: plans.length > 1 ? b.goal_title : '',
      minutes: b.minutes,
      done: b.done,
    }));
  const remaining = todayBlocks.filter((b) => !b.done).length;

  const hours = s.hours || [];
  const peak = Math.max(0, ...hours.map((h) => h.value));
  const peakLabel = hours.find((h) => h.value === peak && peak > 0)?.label;

  return (
    <>
      {header(
        !hasPlan
          ? '아직 확정한 계획이 없어요'
          : todayBlocks.length === 0
            ? '오늘은 놓인 블록이 없어요'
            : remaining > 0
              ? `오늘 ${remaining}개 남았어요`
              : '오늘 할 일을 다 마쳤어요',
      )}

      {/* 목표·마감·이번 주 학습은 레벨과 무관하게 항상 보인다 */}
      {primary && (
        <ProfileSummary
          user={user}
          goal={goalView(primary, today, s.week_planned_minutes)}
          levelName={s.level_name}
          weekMinutes={s.week_minutes}
        />
      )}

      <div className="cols">
        <div className="col col-main">
          <section className="sec">
            <SectionTitle moreHref="/schedule">오늘의 학습</SectionTitle>
            {!hasPlan ? (
              <EmptyState
                title="목표를 정하고 계획을 만들어 보세요"
                description="관심분야와 공부할 수 있는 시간을 알려 주시면 목표를 찾고, AI가 공부 단위로 나눠 빈 시간에 놓아 드립니다."
                action={<Link className="btn btn-primary btn-sm" href="/onboarding">목표 정하기</Link>}
              />
            ) : todayBlocks.length === 0 ? (
              <EmptyState
                title="오늘은 쉬는 날이에요"
                description="주 1일은 휴식일로 비워 둡니다. 다음 블록은 일정에서 확인할 수 있어요."
                action={<Link className="btn btn-green btn-sm" href="/schedule">일정 보기</Link>}
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
                  <span className="stat-value">{s.streak_days}<small>일</small></span>
                </div>
                <div className="stat">
                  <span className="stat-label">이번 주</span>
                  <span className="stat-value">{Math.round((s.week_minutes / 60) * 10) / 10}<small>시간</small></span>
                </div>
                <div className="stat">
                  <span className="stat-label">누적</span>
                  <span className="stat-value">{Math.round(s.total_minutes / 60)}<small>시간</small></span>
                </div>
              </div>
              {s.week_rate !== null && s.week_rate !== undefined && (
                <p className="hint">이번 주 계획한 블록 시간의 {s.week_rate}%를 끝냈어요.</p>
              )}
            </section>
          )}

          {/* 레벨 3 — 목표마다 진도 신호등 (목표는 최대 2개) */}
          {isOpen(level, 'pace') && plans.map((p) => (
            <PaceSignal key={p.plan_id} goal={goalView(p, today)} pace={paceOf(p, today)} milestones={milestones(p)} />
          ))}
        </div>

        {/* PC에서는 기록 계열을 오른쪽 기둥으로 보낸다. 모바일에서는 그대로 아래로 이어진다 */}
        <div className="col col-side">
          {/* 레벨 4 — 학습 잔디 */}
          {isOpen(level, 'grass') && s.history?.length > 0 && (
            <section className="sec">
              <SectionTitle>학습 기록</SectionTitle>
              <StudyGrass history={s.history} weeks={16} />
            </section>
          )}

          {/* 레벨 4 — 시간대 패턴 */}
          {isOpen(level, 'pattern') && (
            <section className="sec">
              <SectionTitle>언제 잘 되나요</SectionTitle>
              {peak === 0 ? (
                <p className="hint">학습 기록이 쌓이면 자주 공부하는 시간대를 보여 드려요.</p>
              ) : (
                <>
                  <div>
                    <div className="pattern">
                      {hours.map((h) => (
                        <div
                          key={h.label}
                          className={h.value === peak ? 'pattern-bar peak' : 'pattern-bar'}
                          style={{ height: Math.round((h.value / peak) * 100) + '%' }}
                          title={h.label + ' · ' + h.value + '회'}
                        />
                      ))}
                    </div>
                    <div className="pattern-labels">
                      {hours.map((h) => (
                        <span key={h.label}>{h.label}</span>
                      ))}
                    </div>
                  </div>
                  <p className="hint">{peakLabel} 무렵에 시작한 학습이 가장 많았습니다.</p>
                </>
              )}
            </section>
          )}

          {/* 레벨 5 — 습관 분석 (학습 메모리의 근거 있는 항목만) */}
          {isOpen(level, 'insight') && (
            <section className="sec">
              <SectionTitle>학습 습관</SectionTitle>
              {habits.length === 0 ? (
                <p className="hint">최근 4주 기록이 3회 이상 쌓이면 습관을 정리해 드려요.</p>
              ) : (
                <div className="rows">
                  {habits.map((h) => (
                    <div className="row" key={h.title}>
                      <div className="row-main">
                        <b>{h.title}</b>
                        <span>{h.detail}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* 레벨 3 — 로그인한 사용자는 관심 분야 추천 */}
          {isOpen(level, 'contests') && (
            <section className="sec">
              <SectionTitle moreHref="/contests">공모전 추천·목록</SectionTitle>
              <DeadlineContests />
            </section>
          )}

          {/* 다음에 무엇이 열리는지 알려준다 — 없으면 그냥 '기능이 없는 화면'이 된다 */}
          {next && level < 5 && (
            <div className="next-level">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span className="tiny" style={{ fontWeight: 600 }}>
                  {next.remainingHours}시간 더 공부하면
                </span>
                <span className="micro dim mono">레벨 {next.level} · {next.name}</span>
              </div>
              <div className="bar">
                <div className="bar-fill" style={{ width: next.percent + '%' }} />
              </div>
              <p className="micro dim">{next.items.join(' · ')}{subjectParticle(next.items.at(-1))} 열립니다</p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
