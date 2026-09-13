import SectionTitle from '@/components/SectionTitle';
import { user, memories, goal } from '@/lib/mock';

// FR-MEM-01 메모리 조회 / FR-MEM-02 메모리 삭제
// FR-MY-01~05 가용시간·목표·알림·탈퇴

const LEVELS = ['입문', '초급', '중급', '상급', '최상급'];

export default function MyPage() {
  return (
    <>
      <header className="stack" style={{ gap: 4 }}>
        <h1 style={{ fontSize: 20 }}>{user.nickname}님</h1>
        <p className="muted tiny">
          레벨 {user.level} {LEVELS[user.level - 1]} · {user.streakDays}일 연속 · 누적{' '}
          {Math.round(user.totalMinutes / 60)}시간
        </p>
      </header>

      <section>
        <SectionTitle>학습 설정</SectionTitle>
        <div className="card rows">
          <div className="row">
            <div className="row-main">
              <b>가용 시간</b>
              <span>주 {goal.weeklyHours}시간 · 다음 재조정부터 반영</span>
            </div>
            <span className="dim">›</span>
          </div>
          <div className="row">
            <div className="row-main">
              <b>목표 관리</b>
              <span>{goal.title} · 기한 {goal.dueDate}</span>
            </div>
            <span className="dim">›</span>
          </div>
          <div className="row">
            <div className="row-main">
              <b>구글 캘린더 연동</b>
              <span>빈 시간대만 읽습니다 · 제목·참석자 미저장</span>
            </div>
            <span className="badge badge-ok">연동됨</span>
          </div>
        </div>
      </section>

      <section>
        <SectionTitle>알림</SectionTitle>
        <div className="card rows">
          <div className="row">
            <div className="row-main">
              <b>알림 강도</b>
              <span>보통 · 시작 알림 + 미완료 독촉</span>
            </div>
            <span className="dim">›</span>
          </div>
          <div className="row">
            <div className="row-main">
              <b>방해금지 시간대</b>
              <span>23:00 ~ 07:00</span>
            </div>
            <span className="dim">›</span>
          </div>
        </div>
      </section>

      <section>
        <SectionTitle>저장된 학습 정보</SectionTitle>
        <div className="card rows">
          {memories.map((m) => (
            <div className="row" key={m.id}>
              <div className="row-main">
                <b>{m.type}</b>
                <span>{m.value} · {m.updatedAt} 갱신</span>
                <span className="dim">근거: {m.basis}</span>
              </div>
              <button className="btn btn-sm">삭제</button>
            </div>
          ))}
        </div>
        <p className="hint" style={{ marginTop: 'var(--gap-2)' }}>
          삭제한 항목은 이후 일정 생성·추천에 사용하지 않습니다 · 되돌릴 수 없습니다
        </p>
      </section>

      <section>
        <div className="card rows">
          <div className="row">
            <div className="row-main">
              <b className="muted">회원 탈퇴</b>
              <span>일정·학습기록·메모리·캘린더 토큰을 모두 삭제합니다</span>
            </div>
            <span className="dim">›</span>
          </div>
        </div>
      </section>
    </>
  );
}
