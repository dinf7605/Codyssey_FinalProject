// FR-UI-01 / FR-UI-02 — 학습량에 따라 화면에 드러나는 정보가 늘어난다.
//
// 처음 온 사람에게 빈 통계와 빈 그래프를 보여주면 '할 게 없는 서비스'로 읽힌다.
// 그래서 레벨 1에서는 오늘 할 일만 보여주고, 기록이 쌓이는 순서대로 구역을 연다.
// 열리는 조건을 미리 알려줘야 다음 목표가 생긴다 — nextUnlock()이 그 역할이다.

export const LEVELS = [
  { level: 1, name: '입문', minHours: 0, unlocks: [] },
  { level: 2, name: '초급', minHours: 10, unlocks: ['streak'] },
  { level: 3, name: '중급', minHours: 30, unlocks: ['pace', 'contests'] },
  { level: 4, name: '상급', minHours: 80, unlocks: ['grass', 'pattern'] },
  { level: 5, name: '최상급', minHours: 150, unlocks: ['insight'] },
];

export const UNLOCK_LABEL = {
  streak: '연속 학습 기록',
  pace: '진도 신호등',
  contests: '맞춤 공모전 추천',
  grass: '학습 기록 잔디',
  pattern: '시간대별 학습 패턴',
  insight: '학습 습관 분석',
};

/** 누적 학습시간(분) -> 레벨 */
export function levelOf(totalMinutes) {
  const hours = totalMinutes / 60;
  let current = LEVELS[0];
  for (const l of LEVELS) if (hours >= l.minHours) current = l;
  return current;
}

/** 이 레벨에서 볼 수 있는 구역인가 */
export function isOpen(level, section) {
  for (const l of LEVELS) {
    if (l.level > level) continue;
    if (l.unlocks.includes(section)) return true;
  }
  return false;
}

/** 다음에 열리는 것 — 남은 시간과 진행률을 함께 준다 */
export function nextUnlock(totalMinutes) {
  const hours = totalMinutes / 60;
  const next = LEVELS.find((l) => hours < l.minHours);
  if (!next) return null;

  const prev = LEVELS[LEVELS.indexOf(next) - 1];
  const span = next.minHours - prev.minHours;
  const done = hours - prev.minHours;

  return {
    level: next.level,
    name: next.name,
    remainingHours: Math.ceil(next.minHours - hours),
    percent: Math.max(0, Math.min(100, Math.round((done / span) * 100))),
    items: next.unlocks.map((u) => UNLOCK_LABEL[u]),
  };
}

/** 특정 레벨에서 바로 다음에 열리는 것 (시간 계산 없이 레벨만 볼 때) */
export function nextFromLevel(level) {
  const next = LEVELS.find((l) => l.level === level + 1);
  if (!next) return null;
  return {
    level: next.level,
    name: next.name,
    remainingHours: null,
    percent: 0,
    items: next.unlocks.map((u) => UNLOCK_LABEL[u]),
  };
}

/** 학습량(분) -> 잔디 색 단계 0~4 */
export function grassLevel(minutes) {
  if (!minutes) return 0;
  if (minutes < 30) return 1;
  if (minutes < 60) return 2;
  if (minutes < 120) return 3;
  return 4;
}
