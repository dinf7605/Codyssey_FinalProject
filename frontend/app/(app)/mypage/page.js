import SectionTitle from '@/components/SectionTitle';
import StudyGrass from '@/components/StudyGrass';
import { levelOf, nextUnlock, LEVELS } from '@/lib/growth';
import { user, memories, goal, studyHistory } from '@/lib/mock';

// FR-MEM-01 메모리 조회 / FR-MEM-02 메모리 삭제 / FR-MY-01~05

export default function MyPage() {
  const current = levelOf(user.totalMinutes);
  const next = nextUnlock(user.totalMinutes);
  const hours = Math.round(user.totalMinutes / 60);

  return (
    <>
      <header className="stack" style={{ gap: 6 }}>
        <p className="tiny dim">레벨 {current.level} · {current.name}</p>
        <h1 className="title">{user.nickname}님</h1>
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
        <SectionTitle>학습 기록</SectionTitle>
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
                <span>{l.unlocks.length ? l.unlocks.join(', ') : '오늘의 학습'}</span>
              </div>
              <span className="mono micro dim">{l.minHours}시간</span>
            </div>
          ))}
        </div>
        <p className="hint">레벨이 오르면 정보 밀도와 강조색이 함께 조절됩니다.</p>
      </section>

      <section className="sec">
        <SectionTitle>학습 설정</SectionTitle>
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
            <span className="pill pill-ok">연동됨</span>
          </div>
          <div className="row">
            <div className="row-main">
              <b>알림 강도</b>
              <span>보통 · 방해금지 23:00~07:00</span>
            </div>
          </div>
        </div>
      </section>

      <section className="sec">
        <SectionTitle>저장된 학습 정보</SectionTitle>
        <div className="rows">
          {memories.map((m) => (
            <div className="row" key={m.id}>
              <div className="row-main">
                <b>{m.type}</b>
                <span>{m.value} · {m.updatedAt} 갱신</span>
                <span className="dim micro">근거: {m.basis}</span>
              </div>
              <button className="btn btn-sm">삭제</button>
            </div>
          ))}
        </div>
        <p className="hint">삭제한 항목은 이후 일정 생성·추천에 사용하지 않습니다 · 되돌릴 수 없습니다</p>
      </section>

      <section className="sec">
        <div className="rows">
          <div className="row">
            <div className="row-main">
              <b className="muted">회원 탈퇴</b>
              <span>일정·학습기록·메모리·캘린더 토큰을 모두 삭제합니다</span>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
