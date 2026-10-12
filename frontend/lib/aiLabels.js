// 관리자 화면의 AI 기록 한글 이름 — ai_call_logs 의 feature · source · model 값은 영어 코드로 저장된다.
// 처리 기록 목록(admin/page.js)과 오늘 AI 사용량(AdminAiBudget)이 같은 이름을 쓰게 여기 모은다.
// 모르는 값이 오면 코드를 그대로 보여 준다 — 새 기능을 붙이고 여기 이름을 안 넣어도 화면이 깨지지 않게.

const FEATURE = {
  'plan.decompose': '학습 분해',
  'goal.match': '목표 추천',
  'contest.recommend': '공모전 추천',
  'study.guide': '블록 공부 방법',
};

const SOURCE = {
  agent: 'AI 에이전트',
  partial: '부분 처리 (일부만 AI)',
  template: '템플릿으로 대체',
  claude: 'AI 처리',
  fallback: 'AI 실패 → 규칙으로 대체',
};

const MODEL = [
  [/sonnet/i, 'Claude Sonnet (주 모델)'],
  [/haiku/i, 'Claude Haiku (빠른 모델)'],
  [/opus/i, 'Claude Opus'],
];

export const featureLabel = (code) => FEATURE[code] || code || '기능 미기록';
export const sourceLabel = (code) => SOURCE[code] || code || '처리 방식 미기록';

export function modelLabel(code) {
  if (!code) return '미기록';
  const hit = MODEL.find(([re]) => re.test(code));
  return hit ? hit[1] : code;
}

export function latencyLabel(ms) {
  if (ms == null) return '미기록';
  return ms < 1000 ? `${ms}밀리초` : `${(ms / 1000).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}초`;
}
