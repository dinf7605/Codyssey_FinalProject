'use client';

import Link from 'next/link';
import { AccountName } from '@/components/CurrentAccount';
import ContestInterestMemory from '@/components/ContestInterestMemory';
import AccountMemories from '@/components/AccountMemories';
import SectionTitle from '@/components/SectionTitle';
import StudyGrass from '@/components/StudyGrass';
import AccountSettings from '@/components/AccountSettings';
import GoalSettings from '@/components/GoalSettings';
import NotificationSettings from '@/components/NotificationSettings';
import { isOpen, nextUnlock, LEVELS, UNLOCK_LABEL } from '@/lib/growth';
import { ddayOf, kstToday } from '@/lib/planView';
import { dday, subjectParticle } from '@/lib/ui';
import { usePlan } from '@/lib/usePlan';
import { useStats } from '@/lib/useStats';

// FR-MEM-01 메모리 조회 / FR-MEM-02 메모리 삭제 / FR-MY-01~05
// 통계·기록은 저장된 학습 기록(/study/stats), 목표는 진행 중 계획(/plan/active)에서 온다.

export default function MyPage() {
  const stats = useStats();
  const plan = usePlan();
  const today = kstToday();

  if (stats.status === 'anon') {
    return (
      <>
        <header className="stack" style={{ gap: 6 }}>
          <h1 className="title">마이페이지</h1>
          <p className="hint">
            로그인하면 학습 기록과 목표, 저장된 학습 정보를 볼 수 있어요.{' '}
            <Link href="/login?next=/mypage">로그인하기</Link>
          </p>
        </header>
      </>
    );
  }

  const s = stats.data;
  const current = s ? { level: s.level, name: s.level_name } : null;
  const next = s ? nextUnlock(s.total_minutes) : null;
  const plans = plan.status === 'ready' ? [...plan.plans].sort((a, b) => a.deadline.localeCompare(b.deadline)) : [];

  return (
    <>
      <header className="stack" style={{ gap: 6 }}>
        <p className="tiny dim">{current ? `레벨 ${current.level} · ${current.name}` : ' '}</p>
        <h1 className="title"><AccountName /></h1>
        {stats.status === 'error' && <p className="hint hint-error">학습 기록을 불러오지 못했어요. {stats.error}</p>}
      </header>

      {s && (
        <section className="sec">
          <div className="stats">
            <div className="stat">
              <span className="stat-label">누적</span>
              {/* 1시간이 안 되면 분으로 — 5분 공부하고 '0시간'이면 기록이 안 된 것처럼 보인다 */}
              {s.total_minutes < 60 ? (
                <span className="stat-value">{s.total_minutes}<small>분</small></span>
              ) : (
                <span className="stat-value">{Math.round(s.total_minutes / 60)}<small>시간</small></span>
              )}
            </div>
            <div className="stat">
              <span className="stat-label">연속</span>
              <span className="stat-value">{s.streak_days}<small>일</small></span>
            </div>
            <div className="stat">
              <span className="stat-label">레벨</span>
              <span className="stat-value">{s.level}<small>/5</small></span>
            </div>
          </div>
          {s.streak_min_minutes > 0 && (
            <p className="micro dim">연속은 하루 {s.streak_min_minutes}분 이상 공부한 날을 이어서 셉니다.</p>
          )}

          {next && (
            <div className="next-level">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span className="tiny" style={{ fontWeight: 600 }}>{next.remainingHours}시간 남음</span>
                <span className="micro dim mono">레벨 {next.level} · {next.name}</span>
              </div>
              <div className="bar">
                <div className="bar-fill" style={{ width: next.percent + '%' }} />
              </div>
              <p className="micro dim">{next.items.join(' · ')}{subjectParticle(next.items.at(-1))} 열립니다</p>
            </div>
          )}
        </section>
      )}

      {/* 잔디는 레벨 4에서 열린다 — 아래 '레벨별로 열리는 것' 표와 대시보드가 같은 규칙을 쓴다 */}
      {s?.history?.length > 0 && isOpen(s.level, 'grass') && (
        <section className="sec">
          <SectionTitle>학습 기록</SectionTitle>
          <StudyGrass history={s.history} weeks={20} />
        </section>
      )}

      <section className="sec">
        <SectionTitle>레벨별로 열리는 것</SectionTitle>
        <div className="rows">
          {LEVELS.map((l) => (
            <div className="row" key={l.level}>
              <div className="row-main">
                <b style={{ color: current && l.level <= current.level ? 'var(--ink)' : 'var(--ink-3)' }}>
                  레벨 {l.level} · {l.name}
                </b>
                <span>{l.unlocks.length ? l.unlocks.map((u) => UNLOCK_LABEL[u]).join(' · ') : '오늘의 학습'}</span>
              </div>
              <span className="mono micro dim">{l.minHours}시간</span>
            </div>
          ))}
        </div>
        <p className="hint">레벨이 오르면 정보 밀도와 강조색이 함께 조절됩니다.</p>
      </section>

      <section className="sec">
        <SectionTitle moreHref="/schedule">진행 중인 목표</SectionTitle>
        {plan.status === 'loading' ? (
          <p className="hint" role="status">불러오는 중…</p>
        ) : plans.length === 0 ? (
          <p className="hint">
            진행 중인 목표가 없어요. <Link href="/schedule">계획 만들기</Link>
          </p>
        ) : (
          <div className="rows">
            {plans.map((p) => (
              <div className="row" key={p.plan_id}>
                <div className="row-main">
                  <b>{p.goal_title}</b>
                  <span>기한 {p.deadline} · 블록 {p.blocks.filter((b) => b.done).length}/{p.blocks.length} 완료</span>
                </div>
                <span className="mono tiny dim">{dday(ddayOf(p.deadline, today))}</span>
              </div>
            ))}
          </div>
        )}
        <div className="rows">
          <div className="row">
            <div className="row-main">
              <b>구글 캘린더 연동</b>
              <span>계획을 만들 때 &lsquo;구글 캘린더에서 바쁜 시간 가져오기&rsquo;를 누르면 그 시간을 피해서 놓아요. 바쁜 시간대만 한 번 읽고 권한은 바로 돌려드려요. 학습 일정은 아래 목표 관리의 &lsquo;내 캘린더에 넣기&rsquo;로 캘린더에 넣을 수 있어요.</span>
            </div>
            {/* 긴 설명 옆에서 버튼이 한 글자씩 세로로 꺾이지 않게 */}
            <Link className="btn btn-sm" style={{ flexShrink: 0, whiteSpace: 'nowrap' }} href="/schedule#plan-builder">계획 만들기</Link>
          </div>
        </div>
      </section>

      {plans.length > 0 && (
        <section className="sec" id="goal-settings">
          <SectionTitle>목표 관리</SectionTitle>
          <GoalSettings plans={plans} />
        </section>
      )}

      <section className="sec" id="notification-settings">
        <SectionTitle>알림 설정</SectionTitle>
        <NotificationSettings />
      </section>

      <ContestInterestMemory />

      <AccountMemories />

      <AccountSettings />
    </>
  );
}
