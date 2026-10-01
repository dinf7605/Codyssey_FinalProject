// 사용자가 원문에서 확인해 직접 입력한 값. 가입 전에는 이 탭의 세션에만 둔다.
const KEY = 'sp_contest_planning';
const TTL_MS = 30 * 60 * 1000;

export function saveContestPlanning({ contestId, title, deadline, field, weeklyHours, weeksNeeded }) {
  if (typeof window === 'undefined') return;
  const record = {
    contestId, title, deadline, field: field || '',
    weeklyHours: Number(weeklyHours), weeksNeeded: Number(weeksNeeded),
    savedAt: Date.now(),
  };
  if (!contestId || !title || !/^\d{4}-\d{2}-\d{2}$/.test(deadline) ||
      !Number.isFinite(record.weeklyHours) || record.weeklyHours <= 0 ||
      !Number.isFinite(record.weeksNeeded) || record.weeksNeeded < 1) {
    throw new Error('공모전 준비 계산값을 확인해 주세요.');
  }
  window.sessionStorage.setItem(KEY, JSON.stringify(record));
}

export function loadContestPlanning() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const record = JSON.parse(raw);
    if (!record.savedAt || Date.now() - record.savedAt > TTL_MS ||
        !record.title || !/^\d{4}-\d{2}-\d{2}$/.test(record.deadline) ||
        !Number.isFinite(record.weeklyHours) || record.weeklyHours <= 0 ||
        !Number.isFinite(record.weeksNeeded) || record.weeksNeeded < 1) {
      window.sessionStorage.removeItem(KEY);
      return null;
    }
    return record;
  } catch {
    return null;
  }
}

export function clearContestPlanning() {
  if (typeof window === 'undefined') return;
  try { window.sessionStorage.removeItem(KEY); } catch { /* 세션 저장소가 차단됨 */ }
}
