// FastAPI 백엔드 호출 래퍼.
// 화면 코드가 fetch를 직접 쓰지 않게 해서, 주소가 바뀌어도 이 파일만 고치면 된다.
//
// 로컬:  NEXT_PUBLIC_API_BASE=http://localhost:8000
// 배포:  Railway 주소 (Vercel 환경변수에 등록 — docs/학습로드맵.md 6-②)

const BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

// 로그인 토큰 보관 위치 — 로그인 화면(담당 E)이 로그인 성공 시 여기에 access_token 을 넣는다.
// 모든 요청이 이 값을 Authorization 헤더로 붙인다. 없으면 비로그인 요청.
export const TOKEN_KEY = 'sp_access_token';

export function getToken() {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(options.headers || {}) },
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

function patch(path, body) {
  return request(path, { method: 'PATCH', body: JSON.stringify(body) });
}

function del(path) {
  return request(path, { method: 'DELETE' });
}

export const api = {
  health: () => request('/health'),

  contests: {
    demoList: (keywords = '', options = {}) =>
      request('/demo/contests?' + new URLSearchParams({ keywords }), options),
  },

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

  // 일정 생성 (FR-PLAN-*, 담당 C)
  plan: {
    // FR-PLAN-02 — 학습 분해 에이전트. 최대 60초가 걸려서 진행 단계를 받아 가며 기다린다.
    // onEvent 는 {type: 'thinking' | 'tool' | 'fallback' | ...} 를 받는다.
    // 마지막 줄의 result 를 돌려준다.
    // signal 을 넘기면 화면을 떠날 때 기다리던 요청을 끊을 수 있다.
    decomposeStream: async ({ goalTitle, goalId, availability, today, signal }, onEvent = () => {}) => {
      const res = await fetch(`${BASE}/plan/decompose/stream`, {
        method: 'POST',
        signal,
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          goal_title: goalTitle,
          goal_id: goalId,
          availability,
          today,
        }),
      });
      if (!res.ok || !res.body) {
        throw new Error(`계획을 만들지 못했습니다 (${res.status})`);
      }

      // 한 줄에 JSON 하나씩 온다 (NDJSON). 줄이 쪼개져 도착할 수 있어 남은 조각을 들고 있는다.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let rest = '';
      let result = null;
      for (;;) {
        const { value, done } = await reader.read();
        rest += decoder.decode(value || new Uint8Array(), { stream: !done });
        const lines = rest.split('\n');
        rest = done ? '' : lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === 'result') result = event.result;
          else if (event.type === 'error') throw new Error(event.message);
          else onEvent(event);
        }
        if (done) break;
      }
      if (!result) throw new Error('응답이 중간에 끊겼습니다. 다시 시도해 주세요.');
      return result;
    },

    // FR-PLAN-03 — 학습 단위를 빈 시간에 배치 (LLM 미사용)
    schedule: ({ units, availability, startDay, deadline }) =>
      post('/plan/schedule', { units, availability, start_day: startDay, deadline }),

    // 규칙 검증기 — 겹침·선행 순서·하루 상한·마감 위반 확인
    validate: ({ blocks, units, deadline }) => post('/plan/validate', { blocks, units, deadline }),

    // 공부량이 기한까지 가용시간의 1.5배를 넘는지 + 범위 축소안 (FR-PLAN-02, LLM 미사용)
    scope: ({ units, availability, startDay, deadline }) =>
      post('/plan/scope', { units, availability, start_day: startDay, deadline }),

    // 계획 확정 (로그인 필요). 서버가 규칙을 한 번 더 검사하고 어기면 400.
    // availability 는 야간 재조정이 다시 놓을 때 쓴다.
    save: ({ goalTitle, goalId, deadline, source, units, blocks, availability }) =>
      post('/plan/save', { goal_title: goalTitle, goal_id: goalId, deadline, source, units, blocks, availability }),

    // 진행 중 계획 (로그인 필요). 없으면 null.
    current: () => request('/plan/current'),

    // FR-PLAN-07 — 최근 7일 재조정 내역 / FR-PLAN-06 — 가장 최근 것 되돌리기 1회
    changes: () => request('/plan/changes'),
    undoChanges: (runId) => post(`/plan/changes/${encodeURIComponent(runId)}/undo`, {}),
    // 03:00 을 기다리지 않고 내 계획만 지금 다시 맞춘다
    replanNow: () => post('/plan/replan-now', {}),

    // FR-PLAN-05 — 블록 옮기기. 규칙에 걸리면 applied=false + violations (force 로 강행)
    moveBlock: (blockId, { start, force = false }) =>
      patch(`/plan/blocks/${encodeURIComponent(blockId)}`, { start, force }),
    deleteBlock: (blockId) => del(`/plan/blocks/${encodeURIComponent(blockId)}`),
  },

  // 학습 실행 (FR-STUDY-*, 담당 C) — 로그인 필요
  study: {
    // 타이머 종료 시. 5분 미만은 기록하지 않는다. 본인 블록이면 완료 처리.
    record: ({ blockId = null, startedAt, endedAt, expectedMinutes = null, note = null }) =>
      post('/study/sessions', {
        block_id: blockId,
        started_at: startedAt,
        ended_at: endedAt,
        expected_minutes: expectedMinutes,
        note,
      }),

    // 누적·주간·연속·레벨 + 이번 주 달성률
    stats: () => request('/study/stats'),

    // FR-STUDY-02 — 완료 취소 (24시간 안에만)
    cancelDone: (blockId) => del(`/study/blocks/${encodeURIComponent(blockId)}/done`),
  },
};

export default api;
