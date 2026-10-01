// 온보딩에서 고른 값(FR-GOAL-13 이어받기 세션)을 일정 API 입력으로 바꾼다.
//
// 온보딩은 가용 시간을 '저녁-월': true 처럼 "시간대-요일" 칸으로 받는다.
// 일정 API는 {weekday, start, end} 목록을 받으므로 여기서 한 번만 변환한다.
// 온보딩 값이 없거나 30분이 지나 만료됐으면 목표가 없는 것으로 본다 (goalTitle null) —
// 사용자가 고르지 않은 목표로 계획을 만들지 않는다. 화면이 목표 정하기로 안내한다.

import { loadExploration } from '@/lib/goalSession';
import { loadContestPlanning } from '@/lib/contest-planning';

const DAYS = ['월', '화', '수', '목', '금', '토', '일'];

// 온보딩 화면의 시간대 이름 -> 실제 시각. 온보딩이 이 표로 주간 시간을 세고 칸에 시각을 적는다.
// (예전엔 온보딩이 칸당 2시간으로 따로 세서, 같은 선택이 온보딩 8시간 · 계획 13시간으로 달랐다)
export const BANDS = {
  오전: { start: '09:00', end: '12:00' },
  오후: { start: '14:00', end: '18:00' },
  저녁: { start: '19:00', end: '22:00' },
  밤: { start: '22:00', end: '23:50' },
};

// 가용시간을 못 받았을 때만 쓰는 값 — 평일 저녁 3시간 = 주 15시간
const DEFAULT_SLOTS = [0, 1, 2, 3, 4].map((weekday) => ({ weekday, ...BANDS.저녁 }));

// 기간 정보가 하나도 없을 때 기한을 잡는 주 수 (화면에서 사용자가 바꿀 수 있다)
const FALLBACK_WEEKS = 8;

const toMinutes = (hhmm) => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};

/** 시간대 하나의 길이(시간) — 온보딩 칸에 적는 값 */
export function bandHours(band) {
  const b = BANDS[band];
  return b ? (toMinutes(b.end) - toMinutes(b.start)) / 60 : 0;
}

/** 슬롯 목록의 주간 합계(시간), 소수 첫째 자리까지 */
export function slotsHours(slots) {
  const minutes = slots.reduce((sum, s) => sum + toMinutes(s.end) - toMinutes(s.start), 0);
  return Math.round((minutes / 60) * 10) / 10;
}

export function slotsFromExploration(cells = {}) {
  const slots = [];
  for (const [key, on] of Object.entries(cells)) {
    if (!on) continue;
    const [band, day] = key.split('-');
    const weekday = DAYS.indexOf(day);
    if (weekday < 0 || !BANDS[band]) continue;
    slots.push({ weekday, ...BANDS[band] });
  }
  return slots.sort((a, b) => a.weekday - b.weekday || a.start.localeCompare(b.start));
}

// 직접 입력한 주당 시간을 월~금에 나누되 하루 6시간을 넘기지 않는다.
export function slotsFromWeeklyHours(weeklyHours) {
  let remaining = Math.round(Number(weeklyHours) * 60);
  const slots = [];
  for (let weekday = 0; weekday < 5 && remaining > 0; weekday++) {
    const minutes = Math.min(remaining, Math.ceil(remaining / (5 - weekday)), 360);
    const end = 17 * 60 + minutes;
    slots.push({ weekday, start: '17:00', end: `${String(Math.floor(end / 60)).padStart(2, '0')}:${String(end % 60).padStart(2, '0')}` });
    remaining -= minutes;
  }
  return slots;
}

/** 온보딩 칸 선택('저녁-월': true …)의 주간 합계(시간) — 계획이 쓰는 것과 같은 값 */
export function weeklyHoursOf(cells = {}) {
  return slotsHours(slotsFromExploration(cells));
}

export function toISODate(d) {
  // toISOString 은 UTC 기준이라 한국 새벽에 하루 전 날짜가 나온다
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// 오늘 공부 시간이 이미 시작됐으면 내일부터 놓는다 — 밤 9시에 만든 계획의 첫 블록이
// 이미 지나간 저녁 7시에 놓이지 않게 (백엔드 replan._place_from 과 같은 규칙)
export function firstStudyDay(slots, now = new Date()) {
  const weekday = (now.getDay() + 6) % 7; // 0=월
  const starts = slots.filter((s) => s.weekday === weekday).map((s) => s.start).sort();
  const hhmm = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  if (!starts.length || hhmm <= starts[0]) return toISODate(now);
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return toISODate(tomorrow);
}

const addDays = (iso, days) => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return toISODate(d);
};

/** 시작일부터 기한까지 몇 주인지 (반올림, 최소 1) */
export function weeksBetween(startDay, deadline) {
  const days = (new Date(`${deadline}T00:00:00`) - new Date(`${startDay}T00:00:00`)) / 86400000;
  return Math.max(1, Math.round(days / 7));
}

/** 권장 주 수를 화면에 보일 정수로 — 온보딩 카드·확정 화면·계획 기한이 같은 값을 쓴다 */
export function plannedWeeks(picked) {
  const weeks = picked?.recommendedWeeks > 0 ? picked.recommendedWeeks : picked?.minWeeks > 0 ? picked.minWeeks : null;
  return weeks ? Math.ceil(weeks) : null;
}

export function planInput(saved = loadExploration(), now = new Date(), contest = loadContestPlanning()) {
  const today = toISODate(now);
  if (contest) {
    const slots = slotsFromWeeklyHours(contest.weeklyHours);
    const startDay = firstStudyDay(slots, now);
    return {
      goalTitle: contest.title,
      goalId: 'custom',
      availability: { slots },
      today,
      startDay,
      deadline: contest.deadline,
      deadlineSource: 'contest',
      tags: [],
      fromOnboarding: true,
      fromContest: true,
    };
  }
  const picked = saved?.picked;
  const cells = slotsFromExploration(saved?.slots);
  const slots = cells.length ? cells : DEFAULT_SLOTS;
  const startDay = firstStudyDay(slots, now);

  // 기한: 시험일(카탈로그 다음 회차) · 직접 입력한 기한 → 없으면 권장 기간으로 잡는다.
  // 이미 지난 날짜면 쓰지 않는다. 어느 쪽이든 계획 화면에서 사용자가 바꿀 수 있다.
  const known = picked?.deadline && picked.deadline > startDay ? picked.deadline : null;
  const deadline = known || addDays(startDay, (plannedWeeks(picked) || FALLBACK_WEEKS) * 7);

  return {
    goalTitle: picked?.title || null,
    // 온보딩은 목표 ID를 넘기지 않는다. 'custom' 이면 에이전트가 카탈로그에서 찾아본다.
    goalId: 'custom',
    availability: { slots },
    today,
    startDay,
    deadline,
    deadlineSource: known ? (picked.source === 'manual' ? 'manual' : 'exam') : 'estimate',
    tags: Array.isArray(saved?.tags) ? saved.tags : [],
    fromOnboarding: cells.length > 0,
    fromContest: false,
  };
}
