// 목표 진행 · 진도 신호등 (FR-MAIN-04 / FR-PACE-01~04) — 진행 중 계획(/plan/active) 하나로 계산한다
//
// 기준선은 직선(기한까지 균등)이 아니라 **확정한 계획** 이다.
// "지금 시각까지 끝났어야 할 블록 수" 와 "실제로 끝낸 블록 수" 를 비교하고,
// 그 차이를 하루에 놓인 평균 블록 수로 나눠 '며칠 앞섬/뒤처짐' 으로 바꾼다.
// 직선 기준을 쓰면 앞쪽에 몰아 놓은 계획이 늘 '앞섬' 으로 보인다.
//
// 야간 재조정이 못 한 블록을 뒤로 옮기면 그만큼 '끝났어야 할 블록' 도 줄어든다 —
// 재조정 뒤에는 새 계획이 기준선이다.

import { addDays, dayKey, ddayOf, kstIso, kstToday, weekdayMon } from './planView';

export const PENDING_DAYS = 3; // 계획을 시작한 지 이보다 짧으면 판정하지 않는다 ('집계 중')

// 단원 = 학습 단위. 그 단위의 블록을 모두 끝냈으면 완료
export function unitProgress(plan) {
  const byUnit = new Map();
  for (const b of plan.blocks) {
    if (!byUnit.has(b.unit_id)) byUnit.set(b.unit_id, []);
    byUnit.get(b.unit_id).push(b);
  }
  const total = plan.units?.length || byUnit.size;
  const done = [...byUnit.values()].filter((list) => list.every((b) => b.done)).length;
  return { done, total };
}

export function paceOf(plan, today = kstToday(), now = kstIso()) {
  const blocks = [...plan.blocks].sort((a, b) => a.start.localeCompare(b.start));
  if (!blocks.length) {
    return { state: 'pending', diffDays: 0, nextCheckpoint: '달력에 놓인 블록이 없어요. 일정에서 다시 놓아 주세요.' };
  }

  const sunday = addDays(today, 6 - weekdayMon(today));
  const leftThisWeek = blocks.filter((b) => !b.done && dayKey(b.start) >= today && dayKey(b.start) <= sunday).length;
  const nextCheckpoint = leftThisWeek
    ? `이번 주 일요일까지 ${leftThisWeek}블록 남았어요`
    : '이번 주 블록을 모두 마쳤어요';

  const elapsedDays = ddayOf(today, dayKey(blocks[0].start));
  if (elapsedDays < PENDING_DAYS) {
    return { state: 'pending', diffDays: 0, nextCheckpoint };
  }

  const due = blocks.filter((b) => b.end <= now).length; // 지금까지 끝났어야 할 블록
  const done = blocks.filter((b) => b.done).length;
  const studyDays = new Set(blocks.map((b) => dayKey(b.start))).size;
  const perDay = blocks.length / studyDays;
  const diffDays = Math.round((done - due) / perDay);
  const state = diffDays >= 1 ? 'ahead' : diffDays <= -1 ? 'late' : 'ontrack';
  return { state, diffDays, nextCheckpoint };
}

// 화면 컴포넌트(ProfileSummary · PaceSignal)가 받는 목표 모양으로 바꾼다
export function goalView(plan, today = kstToday(), weeklyMinutes = 0) {
  const { done, total } = unitProgress(plan);
  return {
    id: plan.plan_id,
    title: plan.goal_title,
    dueDate: plan.deadline,
    dDay: ddayOf(plan.deadline, today),
    unitsDone: done,
    unitsTotal: total,
    weeklyHours: Math.round((weeklyMinutes / 60) * 10) / 10,
  };
}
