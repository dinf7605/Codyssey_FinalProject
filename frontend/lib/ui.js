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
export function paceView(state, diffDays = 0) {
  switch (state) {
    case 'ahead':
      return { tone: 'ok', label: `계획보다 ${diffDays}일 앞섬` };
    case 'late':
      return { tone: 'late', label: `계획보다 ${diffDays}일 뒤처짐` };
    case 'pending':
      return { tone: 'muted', label: '집계 중' };
    case 'ontrack':
    default:
      return { tone: 'ok', label: '계획대로 진행 중' };
  }
}

/** 남은 일수 → 'D-12' 형태 (FR-MAIN-04: 기한이 지나면 D+) */
export function dday(days) {
  if (days === 0) return 'D-DAY';
  return days > 0 ? `D-${days}` : `D+${Math.abs(days)}`;
}
