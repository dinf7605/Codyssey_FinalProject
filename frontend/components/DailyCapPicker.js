'use client';

import { DAILY_CAPS } from '@/lib/planInput';

// 하루 최대 공부 시간 — 온보딩 2단계와 마이페이지 '공부 시간 바꾸기'가 같이 쓴다 (planInput.slotsFromExploration)
export default function DailyCapPicker({ value, onChange }) {
  return (
    <div className="stack" style={{ gap: 6 }}>
      <p className="tiny strong" style={{ margin: 0 }}>하루 최대 공부 시간</p>
      <div role="group" aria-label="하루 최대 공부 시간" style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--gap-2)' }}>
        {DAILY_CAPS.map((cap) => (
          <button
            key={cap.label}
            type="button"
            className="chip"
            aria-pressed={value === cap.value}
            onClick={() => onChange(cap.value)}
          >
            {cap.label}
          </button>
        ))}
      </div>
      <p className="micro dim" style={{ margin: 0 }}>
        칸은 3~4시간이에요. 실제로는 하루 1~2시간이라면 여기서 줄여 주세요 — 고른 칸의 앞부분만 계획에 씁니다.
      </p>
    </div>
  );
}
