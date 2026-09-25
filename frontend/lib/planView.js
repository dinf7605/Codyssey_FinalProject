// 저장된 계획(/plan/current)을 화면에 그리기 위한 계산 — 담당 C
//
// 서버는 블록 시각을 시간대 없는 한국 시각('2026-10-05T19:00:00')으로 준다.
// new Date() 로 바꾸면 브라우저 시간대에 따라 날짜가 밀릴 수 있어서, 문자열을 그대로 자른다.
// 날짜 키는 'YYYY-MM-DD' 문자열 하나로 통일한다.

export const WEEKDAY_MON = ['월', '화', '수', '목', '금', '토', '일'];

export function kstToday() {
  // en-CA 형식이 YYYY-MM-DD 다
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
}

// 서버와 같은 모양의 한국 시각 문자열 '2026-10-05T19:00:00' (sv-SE 형식이 'YYYY-MM-DD HH:mm:ss')
export function kstIso(ms = Date.now()) {
  const text = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).format(new Date(ms));
  return text.replace(' ', 'T');
}

export const dayKey = (iso) => iso.slice(0, 10);
export const hhmm = (iso) => iso.slice(11, 16);

function toUtc(key) {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function fromUtc(date) {
  return date.toISOString().slice(0, 10);
}

export function addDays(key, n) {
  const d = toUtc(key);
  d.setUTCDate(d.getUTCDate() + n);
  return fromUtc(d);
}

export function addMonths(key, n) {
  const d = toUtc(key);
  return fromUtc(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + n, 1)));
}

export const dayNum = (key) => Number(key.slice(8, 10));
export const monthLabel = (key) => `${Number(key.slice(0, 4))}년 ${Number(key.slice(5, 7))}월`;

// 월요일 시작 (0=월 … 6=일)
export const weekdayMon = (key) => (toUtc(key).getUTCDay() + 6) % 7;

export function weekOf(key) {
  const monday = addDays(key, -weekdayMon(key));
  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
}

// 그 달을 덮는 주들. 다른 달 날짜는 null 로 비운다.
export function monthGrid(key) {
  const month = key.slice(0, 7);
  const first = `${month}-01`;
  const weeks = [];
  let monday = addDays(first, -weekdayMon(first));
  while (monday.slice(0, 7) <= month) {
    weeks.push(weekOf(monday).map((k) => (k.slice(0, 7) === month ? k : null)));
    monday = addDays(monday, 7);
  }
  return weeks;
}

export function ddayOf(deadline, today) {
  return Math.round((toUtc(deadline) - toUtc(today)) / 86400000);
}

// FR-PLAN-04 — 완료 · 미완료(지난 날 못 한 것) · 예정
export function blockState(block, today) {
  if (block.done) return 'done';
  return dayKey(block.start) < today ? 'miss' : 'plan';
}

export function blocksByDay(blocks) {
  const map = new Map();
  for (const b of blocks) {
    const key = dayKey(b.start);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(b);
  }
  for (const list of map.values()) list.sort((a, b) => a.start.localeCompare(b.start));
  return map;
}

// DayTimeline 이 받는 모양으로
export function toTimeline(block) {
  return {
    id: block.id,
    start: hhmm(block.start),
    end: hhmm(block.end),
    subject: block.title,
    scope: '',
    minutes: block.minutes,
    done: block.done,
  };
}
