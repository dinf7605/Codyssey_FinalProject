// FastAPI 백엔드 호출 래퍼.
// 화면 코드가 fetch를 직접 쓰지 않게 해서, 주소가 바뀌어도 이 파일만 고치면 된다.
//
// 로컬:  NEXT_PUBLIC_API_BASE=http://localhost:8000
// 배포:  Railway 주소 (Vercel 환경변수에 등록 — docs/학습로드맵.md 6-②)

const BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });

  if (!res.ok) {
    // 에러를 그냥 삼키지 않는다. 화면에서 사용자에게 무엇이 잘못됐는지 보여줘야 한다.
    let detail = `요청이 실패했습니다 (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* 응답이 JSON이 아니면 기본 문구를 쓴다 */
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }

  return res.status === 204 ? null : res.json();
}

function post(path, body) {
  return request(path, { method: 'POST', body: JSON.stringify(body) });
}

export const api = {
  health: () => request('/health'),

  // 아래는 백엔드 라우터가 채워지는 대로 연결한다.
  // 지금은 화면이 목업 데이터로 동작하므로 호출하지 않는다.
  auth: {
    ping: () => request('/auth/ping'),
  },
  batch: {
    ping: () => request('/batch/ping'),
  },

  // 목표 탐색 (FR-GOAL-01~13, 담당 B) — 파이프라인 0
  goal: {
    tags: () => request('/goal/tags'),
    popular: (k = 3) => request(`/goal/popular?k=${k}`),

    // FR-GOAL-11 — 유사 분야 추천 (입력이 없을 때)
    suggest: ({ sessionId, recentGoalTags = [], recentViewedFields = [], isMember = false }) =>
      post('/goal/suggest', {
        session_id: sessionId,
        recent_goal_tags: recentGoalTags,
        recent_viewed_fields: recentViewedFields,
        is_member: isMember,
      }),

    // FR-GOAL-03 — 목표 후보 매칭
    match: ({ tags, sessionId, isMember = false, k = 20 }) =>
      post('/goal/match', { tags, session_id: sessionId, is_member: isMember, k }),

    // FR-GOAL-05 — 목표 추천 카드 (매칭 + 기간 계산 + 추천 이유를 한 번에)
    recommend: ({ tags, weeklyHours, sessionId, isMember = false }) =>
      post('/goal/recommend', {
        tags,
        weekly_hours: weeklyHours,
        session_id: sessionId,
        is_member: isMember,
      }),

    // FR-GOAL-04 · FR-GOAL-09 — 기간 계산 모듈 (LLM 미사용)
    feasibility: ({ candidates, weeklyHours }) =>
      post('/goal/feasibility', { candidates, weekly_hours: weeklyHours }),

    // FR-GOAL-08 — 추천 피드백
    feedback: ({ goalId, interested, reason = null, sessionId }) =>
      post('/goal/feedback', { goal_id: goalId, interested, reason, session_id: sessionId }),

    // FR-GOAL-10 — 직접 입력한 목표의 기한 실현 가능성 확인
    manualCheck: ({ title, dueDate, weeklyHours }) =>
      post('/goal/manual/check', { title, due_date: dueDate, weekly_hours: weeklyHours }),

    // FR-GOAL-07 — 목표 확정
    confirm: ({ goalTitle, isMember = false, activeGoalCount = 0 }) =>
      post('/goal/confirm', {
        goal_title: goalTitle,
        is_member: isMember,
        active_goal_count: activeGoalCount,
      }),

    usage: ({ sessionId, isMember = false }) =>
      request(`/goal/usage?session_id=${encodeURIComponent(sessionId)}&is_member=${isMember}`),
  },
};

export default api;
