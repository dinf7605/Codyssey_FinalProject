// 온보딩에서 고른 값(FR-GOAL-13 이어받기 세션)을 일정 API 입력으로 바꾼다.
//
// 온보딩은 가용 시간을 '저녁-월': true 처럼 "시간대-요일" 칸으로 받는다.
// 일정 API는 {weekday, start, end} 목록을 받으므로 여기서 한 번만 변환한다.
// 온보딩 값이 없거나 30분이 지나 만료됐으면 기본값(평일 저녁)으로 시작한다.

import { loadExploration } from '@/lib/goalSession';

const DAYS = ['월', '화', '수', '목', '금', '토', '일'];

// 온보딩 화면의 시간대 이름 -> 실제 시각. 화면 문구와 같이 바꿔야 한다.
const BANDS = {
  오전: { start: '09:00', end: '12:00' },
  오후: { start: '14:00', end: '18:00' },
  저녁: { start: '19:00', end: '22:00' },
  밤: { start: '22:00', end: '23:50' },
};

// 평일 저녁 3시간 = 주 15시간. 목업 목표의 주간 목표 시간과 같다.
const DEFAULT_SLOTS = [0, 1, 2, 3, 4].map((weekday) => ({ weekday, ...BANDS.저녁 }));

const DEFAULT_GOAL = { title: '정보처리기사 필기', goalId: 'cert-info-eng', weeks: 10 };

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

export function toISODate(d) {
  // toISOString 은 UTC 기준이라 한국 새벽에 하루 전 날짜가 나온다
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function planInput(saved = loadExploration(), now = new Date()) {
  const slots = slotsFromExploration(saved?.slots);
  const picked = saved?.picked;

  const weeks = picked?.recommendedWeeks || picked?.minWeeks || DEFAULT_GOAL.weeks;
  const deadline = new Date(now);
  deadline.setDate(deadline.getDate() + weeks * 7);

  return {
    goalTitle: picked?.title || DEFAULT_GOAL.title,
    // 온보딩은 목표 ID를 넘기지 않는다. 'custom' 이면 에이전트가 카탈로그에서 찾아본다.
    goalId: picked ? 'custom' : DEFAULT_GOAL.goalId,
    availability: { slots: slots.length ? slots : DEFAULT_SLOTS },
    today: toISODate(now),
    deadline: toISODate(deadline),
    weeks,
    fromOnboarding: Boolean(picked || slots.length),
  };
}
