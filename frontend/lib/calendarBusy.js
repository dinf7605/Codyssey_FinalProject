// FR-PLAN-01 구글 캘린더의 바쁜 시간 — 계획을 만들 때 한 번 읽어 이 탭에만 30분 둔다.
//
// 서버는 바쁜 시간도, 구글 토큰도 저장하지 않는다 (backend/routers/google_calendar.py).
// 그래서 여기 보관한 값으로 계획 만들기(/plan/schedule 의 busy)에 넘긴다.
// state 는 구글에 다녀오는 동안 '내가 시작한 연결'인지 확인하는 임의 값이다 (CSRF).

import { api } from './api';

const KEY = 'sp_calendar_busy';
const STATE_KEY = 'sp_calendar_state';
const TTL_MS = 30 * 60 * 1000;

function read(key) {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 저장소가 막혀 있으면 캘린더 없이 계획을 만든다
  }
}

/** 보관한 바쁜 시간 {busy:[{start,end}], startDay, endDay} — 없거나 30분이 지났으면 null */
export function loadBusy() {
  if (typeof window === 'undefined') return null;
  const saved = read(KEY);
  if (!saved?.savedAt || Date.now() - saved.savedAt > TTL_MS || !Array.isArray(saved.busy)) {
    write(KEY, null);
    return null;
  }
  return saved;
}

export function saveBusy({ busy, start_day: startDay, end_day: endDay }) {
  write(KEY, { busy, startDay, endDay, savedAt: Date.now() });
}

export function clearBusy() {
  write(KEY, null);
}

function randomState() {
  const bytes = new Uint8Array(24);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** 구글 동의 화면으로 보낸다. 돌아오면 /calendar/callback 이 이어서 처리한다 */
export async function startCalendarConnect({ startDay, deadline }) {
  const state = randomState();
  const { url } = await api.calendar.connect(state);
  write(STATE_KEY, { state, startDay, endDay: deadline, savedAt: Date.now() });
  window.location.assign(url);
}

/** 돌아온 state 가 내가 보낸 것이면 읽을 기간을, 아니면 null (한 번만 꺼낼 수 있다) */
export function takePending(state) {
  const pending = read(STATE_KEY);
  write(STATE_KEY, null);
  if (!pending || !state || pending.state !== state || Date.now() - pending.savedAt > TTL_MS) return null;
  return { startDay: pending.startDay, endDay: pending.endDay };
}
