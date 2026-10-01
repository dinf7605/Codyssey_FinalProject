// 만든 계획을 확정하기 전까지 보관한다 — 비회원이 로그인하러 다녀오거나, 회원이 다른 화면을 보고 오는 동안.
//
// AI 학습 분해는 1분 가까이 걸린다. 보관하지 않으면 "이 계획으로 확정" → 로그인 → 돌아왔을 때
// 계획이 사라져 처음부터 다시 만들어야 한다 (그동안 Claude 호출도 한 번 더 든다).
// 확정 전 데이터라 contest-planning.js 와 같이 이 탭의 세션에만 30분 둔다.
// 누가 만들었는지(owner)를 붙인다 — 비회원이 만든 것은 로그인한 사람이 이어받고, 다른 계정 것은 버린다.

import { tokenOwner } from './api';

const KEY = 'sp_plan_draft';
const TTL_MS = 30 * 60 * 1000;

// 같은 목표·같은 시작일·같은 기한·같은 가용시간일 때만 되살린다.
// 날이 바뀌었거나(시작일이 달라짐) 다른 목표를 골랐으면 옛 계획을 보여주지 않는다 — 이미 지난 블록이 섞인다.
export function draftKey(input) {
  return JSON.stringify([input.goalTitle, input.goalId, input.startDay, input.deadline, input.availability]);
}

export function saveDraft(key, draft) {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify({ key, savedAt: Date.now(), owner: tokenOwner(), ...draft }));
  } catch {
    // 저장소가 막혀 있으면 보관 없이 간다 — 다시 만들면 된다
  }
}

export function loadDraft() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw);
    const otherAccount = draft.owner && draft.owner !== tokenOwner();
    if (!draft.savedAt || Date.now() - draft.savedAt > TTL_MS || !draft.result?.units || !draft.plan?.blocks || otherAccount) {
      window.sessionStorage.removeItem(KEY);
      return null;
    }
    return draft;
  } catch {
    return null;
  }
}

export function clearDraft() {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // 무시
  }
}
