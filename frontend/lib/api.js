// FastAPI 백엔드 호출 래퍼.
// 화면 코드가 fetch를 직접 쓰지 않게 해서, 주소가 바뀌어도 이 파일만 고치면 된다.
//
// 로컬:  NEXT_PUBLIC_API_BASE=http://localhost:8000
// 배포: Vercel 프론트에서 접근할 API 주소를 환경변수에 등록

const BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

// 로그인 토큰 보관 위치
export const TOKEN_KEY = 'sp_access_token';
export const REFRESH_TOKEN_KEY = 'sp_refresh_token';
export const USER_ID_KEY = 'sp_user_id';

export function setAuthTokens({ accessToken, refreshToken, userId }) {
  if (typeof window === 'undefined') return;

  if (accessToken) {
    window.localStorage.setItem(TOKEN_KEY, accessToken);
  }

  if (refreshToken) {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }

  if (userId) {
    window.localStorage.setItem(USER_ID_KEY, String(userId));
  }
}

export function clearAuthTokens() {
  if (typeof window === 'undefined') return;

  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.localStorage.removeItem(USER_ID_KEY);
}

export function getToken() {
  if (typeof window === 'undefined') return null;

  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

// 토큰(JWT)에 적힌 사용자 id. 기기에 모아 둔 기록이 누구 것인지 가릴 때 쓴다 (서버 검증용 아님).
// 해석할 수 없는 토큰이면 null.
export function tokenOwner(token = getToken()) {
  if (!token) return null;
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(part)).sub || null;
  } catch {
    return null;
  }
}

export function getRefreshToken() {
  if (typeof window === 'undefined') return null;

  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getUserId() {
  if (typeof window === 'undefined') return null;

  try {
    return window.localStorage.getItem(USER_ID_KEY);
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
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    let detail = `요청이 실패했습니다 (${res.status})`;
    let validationErrors = [];

    try {
      const body = await res.json();

      if (typeof body?.detail === 'string') {
        detail = body.detail;
      } else if (Array.isArray(body?.detail)) {
        validationErrors = body.detail;
        detail = body.detail.map((item) => item.msg || JSON.stringify(item)).join('\n');
      }
    } catch {
      // 응답이 JSON이 아니면 기본 문구 사용
    }

    const err = new Error(detail);
    err.status = res.status;
    err.validationErrors = validationErrors;
    throw err;
  }

  if (res.status === 204) {
    return null;
  }

  return res.json();
}

function post(path, body) {
  return request(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

function patch(path, body) {
  return request(path, { method: 'PATCH', body: JSON.stringify(body) });
}

function del(path) {
  return request(path, { method: 'DELETE' });
}

export const api = {
  admin: {
    requestMetrics: ({ day = '' } = {}) => {
      const params = new URLSearchParams();
      if (day) params.set('day', day);
      return request(`/admin/ai-request-metrics?${params}`, { cache: 'no-store' });
    },
    contestInspection: ({ page = 1, pageSize = 20 } = {}) => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      return request(`/admin/contests?${params}`, { cache: 'no-store' });
    },
    // FR-ADMIN-01 수집 공고 고치기 — 보낸 항목만 바뀐다
    fixContest: (id, changes) => patch(`/admin/contests/${encodeURIComponent(id)}`, changes),
    me: () => request('/admin/me'),
    logs: ({ day = '', page = 1, pageSize = 20 } = {}) => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (day) params.set('day', day);
      return request(`/admin/ai-logs?${params}`, { cache: 'no-store' });
    },
    // DB 현황 (읽기 전용) — 테이블별 행 수 · 마지막 기록 / 한 테이블의 최근 행 (개인정보는 가려서 온다)
    dbTables: () => request('/admin/db/tables', { cache: 'no-store' }),
    dbTable: (name, { page = 1, pageSize = 20 } = {}) => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      return request(`/admin/db/tables/${encodeURIComponent(name)}?${params}`, { cache: 'no-store' });
    },
  },
  health: () => request('/health'),

  // 공모전 (담당 D) — 위비티에서 모은 공고. 비회원도 볼 수 있다
  contests: {
    // FR-CONT-03 검색 — query 는 제목·주최에서 찾는다. 기본은 마감 임박순, 마감 지난 공고는 빠진다
    search: ({ query = '', field = '', eligibility = '', deadlineBefore = '', sort = 'deadline', limit = 20 } = {}, options = {}) => {
      const params = new URLSearchParams({ sort, limit: String(limit) });
      if (query) params.set('query', query);
      if (field) params.set('field', field);
      if (eligibility) params.set('eligibility', eligibility);
      if (deadlineBefore) params.set('deadline_before', deadlineBefore);
      return request(`/contests?${params}`, options);
    },
    get: (id) => request(`/contests/${encodeURIComponent(id)}`),
    recommend: (tags = '') => {
      const params = new URLSearchParams();
      if (tags) params.set('tags', tags);
      return request(`/contests/recommendations?${params}`, { cache: 'no-store' });
    },
    feedback: (id, rating, reason = null) =>
      post(`/contests/${encodeURIComponent(id)}/feedback`, { rating, reason }),
    // FR-CONT-10 준비 기간 산정 (LLM 미사용)
    estimate: (id, weeklyHours, details = {}) =>
      post(`/contests/${encodeURIComponent(id)}/estimate`, { weekly_hours: weeklyHours, ...details }),
  },

  memories: {
    list: () => request('/memories', { cache: 'no-store' }),
    saveInterests: (tags) => request('/memories/interest-tags', {
      method: 'PUT', body: JSON.stringify({ tags }),
    }),
    remove: (id) => del(`/memories/${encodeURIComponent(id)}`),
    clear: () => del('/memories'),
  },

  // 인증
  auth: {
    ping: () => request('/auth/ping'),

    signup: ({
      email,
      password,
      nickname,
      agreePrivacy,
      agreeAiNotice,
      agreeMarketing = false,
    }) =>
      post('/auth/signup', {
        email,
        password,
        nickname,
        agree_privacy: agreePrivacy,
        agree_ai_notice: agreeAiNotice,
        agree_marketing: agreeMarketing,
      }),

    login: ({ email, password }) =>
      post('/auth/login', {
        email,
        password,
      }),

    forgotPassword: ({ email }) => post('/auth/forgot-password', { email }),
    resetPassword: ({ accessToken, refreshToken, newPassword }) =>
      post('/auth/reset-password', {
        access_token: accessToken, refresh_token: refreshToken, new_password: newPassword,
      }),
    me: () => request('/auth/me'),

    // FR-AUTH-02 구글 로그인 — backend/routers/auth_google.py
    google: {
      start: (redirectTo) =>
        request(`/auth/google/start?redirect_to=${encodeURIComponent(redirectTo)}`),
      profile: () => request('/auth/google/profile', { cache: 'no-store' }),
      complete: ({ nickname, agreePrivacy, agreeAiNotice, agreeMarketing = false }) =>
        post('/auth/google/complete', {
          nickname,
          agree_privacy: agreePrivacy,
          agree_ai_notice: agreeAiNotice,
          agree_marketing: agreeMarketing,
        }),
    },
  },

  // FR-ALARM-01~04 앱 안 알림 (backend/routers/notifications.py)
  notifications: {
    list: () => request('/notifications', { cache: 'no-store' }),
    read: (id) => patch(`/notifications/${encodeURIComponent(id)}/read`, {}),
    readAll: () => patch('/notifications/read-all', {}),
  },

  settings: {
    // FR-MY-03/05 알림 켜기·N분 전·방해금지·강도
    notifications: () => request('/settings/notifications', { cache: 'no-store' }),
    saveNotifications: (body) => request('/settings/notifications', { method: 'PUT', body: JSON.stringify(body) }),
    profile: () => request('/settings/profile'),
    withdraw: () => request('/settings/withdraw', {
      method: 'DELETE',
      body: JSON.stringify({ confirm: true }),
    }),
  },

  // 배치 확인용
  batch: {
    ping: () => request('/batch/ping'),
  },

  // 목표 탐색
  goal: {
    tags: () => request('/goal/tags'),

    popular: (k = 3) => request(`/goal/popular?k=${k}`),

    suggest: ({ sessionId, recentGoalTags = [], recentViewedFields = [], isMember = false }) =>
      post('/goal/suggest', {
        session_id: sessionId,
        recent_goal_tags: recentGoalTags,
        recent_viewed_fields: recentViewedFields,
        is_member: isMember,
      }),

    match: ({ tags, sessionId, isMember = false, k = 20 }) =>
      post('/goal/match', {
        tags,
        session_id: sessionId,
        is_member: isMember,
        k,
      }),

    recommend: ({ tags, weeklyHours, sessionId, isMember = false }) =>
      post('/goal/recommend', {
        tags,
        weekly_hours: weeklyHours,
        session_id: sessionId,
        is_member: isMember,
      }),

    feasibility: ({ candidates, weeklyHours }) =>
      post('/goal/feasibility', {
        candidates,
        weekly_hours: weeklyHours,
      }),

    feedback: ({ goalId, interested, reason = null, sessionId }) =>
      post('/goal/feedback', {
        goal_id: goalId,
        interested,
        reason,
        session_id: sessionId,
      }),

    // FR-GOAL-08 — "관심없음" 피드백 취소. 회원이면 토큰으로, 비회원이면 sessionId로
    // 본인 기록만 지운다(백엔드가 확인).
    cancelFeedback: ({ goalId, sessionId }) =>
      del(`/goal/feedback/${encodeURIComponent(goalId)}?session_id=${encodeURIComponent(sessionId)}`),

    // FR-GOAL-08 — 지금 "관심없음"으로 빠져 있는 목표 목록(추천 화면 하단 섹션).
    dismissedFeedback: ({ sessionId }) =>
      request(`/goal/feedback/dismissed?session_id=${encodeURIComponent(sessionId)}`),

    manualCheck: ({ title, dueDate, weeklyHours }) =>
      post('/goal/manual/check', {
        title,
        due_date: dueDate,
        weekly_hours: weeklyHours,
      }),

    confirm: ({ goalTitle, isMember = false, activeGoalCount = 0 }) =>
      post('/goal/confirm', {
        goal_title: goalTitle,
        is_member: isMember,
        active_goal_count: activeGoalCount,
      }),

    usage: ({ sessionId, isMember = false }) =>
      request(`/goal/usage?session_id=${encodeURIComponent(sessionId)}&is_member=${isMember}`),
  },

   // 일정 생성
  plan: {
    // 학습 분해 스트림
    decomposeStream: async (
      { goalTitle, goalId, availability, today, signal },
      onEvent = () => {}
    ) => {
      const res = await fetch(`${BASE}/plan/decompose/stream`, {
        method: 'POST',
        signal,
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
        },
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

      // 한 줄에 JSON 하나씩 오는 NDJSON 응답 처리
      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      let rest = '';
      let result = null;

      for (;;) {
        const { value, done } = await reader.read();

        rest += decoder.decode(value || new Uint8Array(), {
          stream: !done,
        });

        const lines = rest.split('\n');
        rest = done ? '' : lines.pop();

        for (const line of lines) {
          if (!line.trim()) continue;

          const event = JSON.parse(line);

          if (event.type === 'result') {
            result = event.result;
          } else if (event.type === 'error') {
            throw new Error(event.message);
          } else {
            onEvent(event);
          }
        }

        if (done) break;
      }

      if (!result) {
        throw new Error('응답이 중간에 끊겼습니다. 다시 시도해 주세요.');
      }

      return result;
    },

    // 로그인 상태면 서버가 진행 중인 다른 목표의 블록을 피해서 놓는다. goalTitle 은 다시 만드는 같은 목표를 빼려고
    schedule: ({ units, availability, startDay, deadline, goalTitle = null }) =>
      post('/plan/schedule', {
        units,
        availability,
        start_day: startDay,
        deadline,
        goal_title: goalTitle,
      }),

    validate: ({ blocks, units, deadline }) =>
      post('/plan/validate', {
        blocks,
        units,
        deadline,
      }),

    // 공부량이 기한까지 가용시간의 1.5배를 넘는지 + 범위 축소안 (FR-PLAN-02, LLM 미사용)
    scope: ({ units, availability, startDay, deadline }) =>
      post('/plan/scope', { units, availability, start_day: startDay, deadline }),

    // 계획 확정 (로그인 필요). 서버가 규칙을 한 번 더 검사하고 어기면 400.
    // availability 는 야간 재조정이 다시 놓을 때 쓴다.
    save: ({ goalTitle, goalId, deadline, source, units, blocks, availability }) =>
      post('/plan/save', { goal_title: goalTitle, goal_id: goalId, deadline, source, units, blocks, availability }),

    current: () => request('/plan/current'),

    // 진행 중 계획 전부 — 목표는 동시에 최대 2개 (FR-GOAL-07). { plans, max_plans }
    active: () => request('/plan/active'),

    // 목표 끝내기 — 계획을 보관한다. 학습 기록은 남는다
    archive: (planId) => post(`/plan/${encodeURIComponent(planId)}/archive`, {}),

    // FR-PLAN-04 — 미배치 단원을 오늘 이후 빈 시간에 넣어 본다. { placed, left, blocks }
    placeUnplaced: (planId) => post(`/plan/${encodeURIComponent(planId)}/place-unplaced`, {}),

    // FR-PLAN-07 — 최근 7일 재조정 내역 / FR-PLAN-06 — 가장 최근 것 되돌리기 1회
    changes: () => request('/plan/changes'),
    undoChanges: (runId) => post(`/plan/changes/${encodeURIComponent(runId)}/undo`, {}),
    // 03:00 을 기다리지 않고 내 계획만 지금 다시 맞춘다
    replanNow: () => post('/plan/replan-now', {}),

    // FR-PLAN-05 — 블록 옮기기. 규칙에 걸리면 applied=false + violations (force 로 강행)
    moveBlock: (blockId, { start, force = false }) =>
      patch(`/plan/blocks/${encodeURIComponent(blockId)}`, { start, force }),
    deleteBlock: (blockId) => del(`/plan/blocks/${encodeURIComponent(blockId)}`),
    // FR-PLAN-08 내 캘린더로 내보내기 — .ics 파일(Blob)을 받는다. 화면이 저장 창을 띄운다
    calendarFile: async (planId) => {
      const res = await fetch(`${BASE}/plan/${encodeURIComponent(planId)}/calendar.ics`, { headers: authHeaders() });
      if (!res.ok) {
        const err = new Error('캘린더 파일을 만들지 못했어요.');
        err.status = res.status;
        throw err;
      }
      return res.blob();
    },
    // FR-ALARM-03 알림에서 미루기 — 다음 날 이후 빈 시간으로, 뒤 단원도 순서대로 함께
    postponeBlock: (blockId) => post(`/plan/blocks/${encodeURIComponent(blockId)}/postpone`, {}),
    // FR-MY-01 공부 가능 시간 바꾸기 — 앞으로의 블록을 새 시간에 다시 놓는다
    changeAvailability: (planId, availability) =>
      request(`/plan/${encodeURIComponent(planId)}/availability`, { method: 'PUT', body: JSON.stringify(availability) }),
  },

  // 학습 실행
  study: {
    // markDone=false — 시간만 남기고 블록은 완료하지 않는다 (예상보다 훨씬 짧게 하고 멈춘 경우)
    record: ({ blockId = null, startedAt, endedAt, expectedMinutes = null, note = null, markDone = true }) =>
      post('/study/sessions', {
        block_id: blockId,
        started_at: startedAt,
        ended_at: endedAt,
        expected_minutes: expectedMinutes,
        note,
        mark_done: markDone,
      }),

    // 누적·주간·연속·레벨 + 이번 주 달성률
    stats: () => request('/study/stats'),

    // FR-STUDY-02 — 완료 취소 (24시간 안에만)
    cancelDone: (blockId) => del(`/study/blocks/${encodeURIComponent(blockId)}/done`),

    // FR-STUDY-05 — 학습 메모를 목표별로 모아보기. { groups: [{ plan_id, goal_title, active, notes }] }
    notes: () => request('/study/notes'),
  },
};

export default api;
