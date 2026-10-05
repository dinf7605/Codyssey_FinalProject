// 적응형 UI 계산 (FR-UI-01 테마 / FR-UI-02 정보 밀도)
//
// 규칙은 기능명세서를 그대로 옮겼다.
//   레벨 1~2 → 요약형(compact) / 레벨 3 → 보통 / 레벨 4~5 → 상세형(comfortable)
// 사용자가 마이페이지에서 수동 고정하면 그 값이 자동 조절보다 우선한다.

export function densityForLevel(level, manual) {
  if (manual) return manual;              // 수동 설정 우선 (FR-UI-02)
  if (level <= 2) return 'compact';
  if (level >= 4) return 'comfortable';
  return 'normal';
}

/** 진도 상태 → 화면에 쓸 색 이름과 문구.
 *  색만으로 구분하지 않도록 항상 label을 함께 반환한다 (NFR-A11Y-01). */
export function paceView(state, diffDays = 0, level = null) {
  switch (state) {
    case 'ahead':
      return { tone: 'ok', label: `계획보다 ${diffDays}일 앞섬` };
    case 'late':
      // FR-PACE-03 — 3일 이상 주의, 7일 이상 경고
      return { tone: 'late', label: `${level === 'warning' ? '경고' : '주의'} · 계획보다 ${diffDays}일 뒤처짐` };
    case 'pending':
      return { tone: 'muted', label: '집계 중' };
    case 'ontrack':
    default:
      return { tone: 'ok', label: '계획대로 진행 중' };
  }
}

/** 받침에 맞는 조사 — '연속 학습 기록이', '학습 패턴이' / 받침 없으면 '가'. 한글이 아니면 '이(가)' */
export function subjectParticle(word) {
  const code = (word || '').trim().slice(-1).charCodeAt(0) - 0xac00;
  if (Number.isNaN(code) || code < 0 || code > 11171) return '이(가)';
  return code % 28 ? '이' : '가';
}

// 블록 하나의 최대 길이 — backend/schemas/plan.py MAX_BLOCK_MINUTES 와 같아야 한다
const MAX_BLOCK_MINUTES = 120;

/** 학습 단위 시간 → '90분' 또는 '6시간 · 블록 3개' (120분이 넘는 단위는 블록 여러 개로 나뉘어 놓인다) */
export function unitLength(minutes) {
  if (minutes <= MAX_BLOCK_MINUTES) return `${minutes}분`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}시간${m ? ` ${m}분` : ''} · 블록 ${Math.ceil(minutes / MAX_BLOCK_MINUTES)}개`;
}

/** 받침에 맞는 목적격 조사 — '관심 분야를', '학습 기록을' / 한글이 아니면 '을(를)' */
export function objectParticle(word) {
  const code = (word || '').trim().slice(-1).charCodeAt(0) - 0xac00;
  if (Number.isNaN(code) || code < 0 || code > 11171) return '을(를)';
  return code % 28 ? '을' : '를';
}

/** 받침에 맞는 보조사 — '공모전은', '정보처리기사는' / 한글이 아니면(괄호·영문으로 끝나면) '은(는)' */
export function topicParticle(word) {
  const code = (word || '').trim().slice(-1).charCodeAt(0) - 0xac00;
  if (Number.isNaN(code) || code < 0 || code > 11171) return '은(는)';
  return code % 28 ? '은' : '는';
}

/** 남은 일수 → 'D-12' 형태 (FR-MAIN-04: 기한이 지나면 D+) */
export function dday(days) {
  if (days === 0) return 'D-DAY';
  return days > 0 ? `D-${days}` : `D+${Math.abs(days)}`;
}
