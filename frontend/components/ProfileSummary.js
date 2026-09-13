import { dday } from '@/lib/ui';

// 로그인 후 첫 화면의 기준점.
//
// 목표와 남은 기간은 '쌓아서 얻는 정보'가 아니라 사용자가 직접 넣은 값이다.
// 그래서 레벨과 무관하게 항상 보여준다 — 이 서비스가 답하기로 한 질문
// ("기한 안에 끝낼 수 있나")이 바로 여기에 있다.
// 반대로 진도 신호등(앞섬/지연 판정)은 며칠치 기록이 있어야 계산되므로 레벨 3에서 열린다.

export default function ProfileSummary({ user, goal, levelName, weekMinutes }) {
  const weekHours = Math.round((weekMinutes / 60) * 10) / 10;
  const weekPercent = Math.min(100, Math.round((weekMinutes / 60 / goal.weeklyHours) * 100));
  const totalHours = Math.round(user.totalMinutes / 60);

  return (
    <section className="panel profile" aria-label="내 학습 현황">
      <div className="profile-head">
        <div className="stack" style={{ gap: 3, minWidth: 0 }}>
          <span className="profile-name">{user.nickname}님</span>
          <span className="tiny dim">레벨 {levelName}</span>
        </div>
        <div className="stack profile-goal">
          <span className="profile-goal-title">{goal.title}</span>
          <span className="micro dim mono">{goal.dueDate} 마감</span>
        </div>
      </div>

      <div className="profile-dday">
        <span className="num-big">{dday(goal.dDay)}</span>
        <span className="tiny dim">시험일까지</span>
      </div>

      {/* 주당 학습시간 목표 — 이번 주 얼마나 채웠는지 */}
      <div className="profile-week">
        <div className="profile-week-top">
          <span className="tiny muted">이번 주 학습</span>
          <span className="mono tiny">
            <b>{weekHours}</b> / {goal.weeklyHours}시간
          </span>
        </div>
        <div
          className="bar"
          role="progressbar"
          aria-valuenow={weekPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="이번 주 학습시간 목표 달성률"
        >
          <div className="bar-fill" style={{ width: weekPercent + '%' }} />
        </div>
      </div>

      <div className="profile-stats">
        <div className="profile-stat">
          <span className="profile-stat-value mono">{totalHours}</span>
          <span className="micro dim">누적 시간</span>
        </div>
        <div className="profile-stat">
          <span className="profile-stat-value mono">{user.streakDays}</span>
          <span className="micro dim">연속 일수</span>
        </div>
        <div className="profile-stat">
          <span className="profile-stat-value mono">
            {goal.unitsDone}<span className="profile-stat-sub">/{goal.unitsTotal}</span>
          </span>
          <span className="micro dim">완료 단원</span>
        </div>
      </div>
    </section>
  );
}
