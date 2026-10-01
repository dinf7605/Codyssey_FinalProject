import { AccountName } from '@/components/CurrentAccount';
import ContestInterestMemory from '@/components/ContestInterestMemory';
import AccountMemories from '@/components/AccountMemories';
import SectionTitle from '@/components/SectionTitle';
import StudyGrass from '@/components/StudyGrass';
import AccountSettings from '@/components/AccountSettings';
import { levelOf, nextUnlock, LEVELS, UNLOCK_LABEL } from '@/lib/growth';
import { user, goal, studyHistory } from '@/lib/mock';

// FR-MEM-01 메모리 조회 / FR-MEM-02 메모리 삭제 / FR-MY-01~05

export default function MyPage() {
  const current = levelOf(user.totalMinutes);
  const next = nextUnlock(user.totalMinutes);
  const hours = Math.round(user.totalMinutes / 60);

  return (
    <>
      <header className="stack" style={{ gap: 6 }}>
        <p className="tiny dim">예시 레벨 {current.level} · {current.name}</p>
        <h1 className="title"><AccountName /></h1>
        <p className="hint">학습 통계·기록·설정은 예시입니다. 저장된 학습 정보와 계정 정보는 아래에서 확인할 수 있습니다.</p>
      </header>

      <section className="sec">
        <div className="stats">
          <div className="stat">
            <span className="stat-label">누적</span>
            <span className="stat-value">{hours}<small>시간</small></span>
          </div>
          <div className="stat">
            <span className="stat-label">연속</span>
            <span className="stat-value">{user.streakDays}<small>일</small></span>
          </div>
          <div className="stat">
            <span className="stat-label">레벨</span>
            <span className="stat-value">{current.level}<small>/5</small></span>
          </div>
        </div>

        {next && (
          <div className="next-level">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span className="tiny" style={{ fontWeight: 600 }}>{next.remainingHours}시간 남음</span>
              <span className="micro dim mono">레벨 {next.level} · {next.name}</span>
            </div>
            <div className="bar">
              <div className="bar-fill" style={{ width: next.percent + '%' }} />
            </div>
            <p className="micro dim">{next.items.join(' · ')}이(가) 열립니다</p>
          </div>
        )}
      </section>

      <section className="sec">
        <SectionTitle>학습 기록 (예시)</SectionTitle>
        <StudyGrass history={studyHistory} weeks={20} />
      </section>

      <section className="sec">
        <SectionTitle>레벨별로 열리는 것</SectionTitle>
        <div className="rows">
          {LEVELS.map((l) => (
            <div className="row" key={l.level}>
              <div className="row-main">
                <b style={{ color: l.level <= current.level ? 'var(--ink)' : 'var(--ink-3)' }}>
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
        <SectionTitle>학습 설정 (예시)</SectionTitle>
        <div className="rows">
          <div className="row">
            <div className="row-main">
              <b>가용 시간</b>
              <span>주 {goal.weeklyHours}시간 · 다음 재조정부터 반영</span>
            </div>
          </div>
          <div className="row">
            <div className="row-main">
              <b>목표 관리</b>
              <span>{goal.title} · 기한 {goal.dueDate}</span>
            </div>
          </div>
          <div className="row">
            <div className="row-main">
              <b>구글 캘린더 연동</b>
              <span>빈 시간대만 읽습니다 · 제목·참석자 미저장</span>
            </div>
            <span className="pill">예시: 연동됨</span>
          </div>
          <div className="row">
            <div className="row-main">
              <b>알림 강도</b>
              <span>보통 · 방해금지 23:00~07:00</span>
            </div>
          </div>
        </div>
      </section>

      <ContestInterestMemory />

      <AccountMemories />

      <AccountSettings />
    </>
  );
}
