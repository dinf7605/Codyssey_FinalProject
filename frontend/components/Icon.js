// 탭과 목록에 쓰는 선 아이콘.
// 기호 문자(◉ ▦ ◈)는 기기·폰트마다 다르게 보이고 미완성처럼 읽혀서 SVG로 직접 그린다.

const base = {
  width: 24,
  height: 24,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': 'true',
};

export function IconToday(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 1.8" />
    </svg>
  );
}

export function IconSchedule(props) {
  return (
    <svg {...base} {...props}>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 9.5h17M8 3.5v3M16 3.5v3" />
      <path d="M7.5 13.5h3M7.5 16.5h6" />
    </svg>
  );
}

export function IconContest(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3.5l2.6 5.4 5.9.85-4.25 4.16 1 5.89L12 17.03l-5.25 2.77 1-5.89L3.5 9.75l5.9-.85z" />
    </svg>
  );
}

export function IconMe(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="8" r="3.75" />
      <path d="M4.5 20c0-3.6 3.36-6.25 7.5-6.25s7.5 2.65 7.5 6.25" />
    </svg>
  );
}

export function IconCheck(props) {
  return (
    <svg {...base} strokeWidth={2.2} {...props}>
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}
