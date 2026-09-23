// 목표 탐색(FR-GOAL-*)에서만 쓰는 로컬 저장소 도우미.
//
//  getAnonSessionId() — FR-GOAL-12 비회원 AI 호출 한도를 세션 단위로 세기 위한 익명 ID.
//                        로그인 여부와 무관하게 기기에 하나만 만들어 계속 쓴다.
//  saveExploration()  — FR-GOAL-13 가입 후 이어받기. 관심 태그·가용시간·고른 목표를
//                        30분짜리 세션으로 저장해 뒀다가, 가입이 끝나면 그대로 이어받는다.
//                        (지금은 가입 제출 동작이 아직 연결되지 않았으므로, 이 파일은
//                        저장까지만 하고 실제로 읽어서 계정에 반영하는 쪽은 인증이
//                        붙는 대로 signup 쪽에서 loadExploration()을 부르면 된다.)

const ANON_KEY = 'sp_goal_anon_session';
const EXPLORATION_KEY = 'sp_goal_exploration';
const EXPLORATION_TTL_MS = 30 * 60 * 1000; // FR-GOAL-13: 세션 만료 30분

function randomId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `anon-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function getAnonSessionId() {
  if (typeof window === 'undefined') return 'server';
  try {
    let id = window.localStorage.getItem(ANON_KEY);
    if (!id) {
      id = randomId();
      window.localStorage.setItem(ANON_KEY, id);
    }
    return id;
  } catch {
    // 프라이빗 모드 등으로 localStorage를 못 쓰면 매 호출마다 새 세션으로 본다.
    return randomId();
  }
}

export function saveExploration(payload) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      EXPLORATION_KEY,
      JSON.stringify({ ...payload, savedAt: Date.now() })
    );
  } catch {
    /* 저장에 실패해도 온보딩 흐름 자체는 막지 않는다 */
  }
}

export function loadExploration() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(EXPLORATION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data.savedAt || Date.now() - data.savedAt > EXPLORATION_TTL_MS) {
      window.localStorage.removeItem(EXPLORATION_KEY);
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

export function clearExploration() {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(EXPLORATION_KEY);
  } catch {
    /* noop */
  }
}
