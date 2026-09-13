// 화면을 눈으로 확인하기 위한 임시 데이터.
// 백엔드가 연결되면 이 파일을 지우고 lib/api.js 호출로 바꾼다.
// 값은 전부 예시이며 실제 사용자 데이터가 아니다.

export const user = {
  nickname: '지훈',
  level: 3,          // FR-STUDY-04 — 누적 학습시간 5단계
  streakDays: 12,    // FR-STUDY-04 — 하루 20분 이상이면 유지
  totalMinutes: 2840,
};

export const goal = {
  id: 'g-info-eng',
  title: '정보처리기사 필기',
  dueDate: '2026-12-06',
  dDay: 83,
  unitsDone: 14,
  unitsTotal: 42,
  weeklyHours: 15,
};

// FR-PACE-02 / FR-PACE-04 — 진도 신호등
// state: 'ahead' | 'ontrack' | 'late' | 'pending'
export const pace = {
  state: 'ontrack',
  diffDays: 0,
  nextCheckpoint: '이번 주 일요일까지 3단원 완료',
};

// FR-MAIN-03 — 오늘 배정된 학습 블록
export const todayBlocks = [
  { id: 'b1', start: '09:00', end: '10:00', subject: '소프트웨어 설계', scope: '2단원 요구사항 확인', minutes: 60, done: true },
  { id: 'b2', start: '14:00', end: '15:30', subject: '데이터베이스 구축', scope: '3단원 물리 데이터베이스', minutes: 90, done: false },
  { id: 'b3', start: '20:00', end: '21:00', subject: '기출 풀이', scope: '2023년 2회차 1~40번', minutes: 60, done: false },
];

// FR-CONT-04 / FR-CONT-05 — 주간 공모전 추천
export const contests = [
  {
    id: 'c1',
    title: '제12회 공공데이터 활용 아이디어 공모전',
    host: '한국지능정보사회진흥원',
    field: 'IT·데이터',
    deadline: '2026-10-05',
    dDay: 21,
    reason: '진행 중인 목표와 분야가 겹치고, 남은 준비 기간이 최소 필요 기간을 넘습니다.',
    tags: ['데이터분석', '기획'],
    aiGenerated: true,
  },
  {
    id: 'c2',
    title: '대학생 SW 개발 경진대회',
    host: '정보통신산업진흥원',
    field: 'IT·개발',
    deadline: '2026-10-24',
    dDay: 40,
    reason: '지원 자격의 재학 요건을 충족하며 마감까지 여유가 있습니다.',
    tags: ['웹개발', '팀프로젝트'],
    aiGenerated: true,
  },
  {
    id: 'c3',
    title: '오픈소스 컨트리뷰션 아카데미',
    host: '정보통신산업진흥원',
    field: 'IT·개발',
    deadline: '2026-09-30',
    dDay: 16,
    reason: '학습 중인 과목과 연관이 있으나 준비 기간이 빠듯합니다.',
    tags: ['오픈소스'],
    aiGenerated: true,
  },
];

// FR-GOAL-05 — 목표 추천 카드
export const goalSuggestions = [
  {
    id: 'gs1',
    title: '정보처리기사 필기',
    weeks: 12,
    hoursPerWeek: 12,
    reason: '입력하신 관심 분야와 가장 가깝고, 주 12시간이면 시험일 안에 준비를 마칠 수 있습니다.',
  },
  {
    id: 'gs2',
    title: 'SQLD (SQL 개발자)',
    weeks: 6,
    hoursPerWeek: 8,
    reason: '데이터 분야 입문 자격증으로 준비 기간이 짧아 병행이 가능합니다.',
  },
  {
    id: 'gs3',
    title: '공공데이터 활용 공모전',
    weeks: 8,
    hoursPerWeek: 10,
    reason: '포트폴리오로 이어지며 마감일이 가용 기간 안에 들어옵니다.',
  },
];

// FR-MEM-01 — 시스템이 저장한 개인화 정보
export const memories = [
  { id: 'm1', type: '선호 학습 시간대', value: '평일 20~22시', updatedAt: '2026-09-12', basis: '최근 10회 블록 완료 시각' },
  { id: 'm2', type: '예상 대비 실제 소요시간', value: '평균 +18%', updatedAt: '2026-09-13', basis: '완료한 14개 학습 단위' },
  { id: 'm3', type: '관심 태그', value: '데이터분석, 백엔드', updatedAt: '2026-09-10', basis: '목표·공모전 조회 이력' },
];

export const interestTags = [
  'IT·개발', '데이터분석', '디자인', '마케팅', '기획', '금융', '어학', '공모전', '포트폴리오',
];
