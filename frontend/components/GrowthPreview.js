'use client';

import { LEVELS } from '@/lib/growth';
import { densityForLevel } from '@/lib/ui';

// 개발·발표용 도구. 학습 기록을 쌓지 않고도 레벨별 화면을 확인할 수 있게 한다.
// 실제 서비스에서는 레벨이 누적 학습시간으로만 정해지므로 배포 전에 제거한다.

export default function GrowthPreview({ level, onChange }) {
  function pick(next) {
    onChange(next);
    const root = document.documentElement;
    root.dataset.level = String(next);
    root.dataset.density = densityForLevel(next);
  }

  return (
    <div className="devbar">
      <label htmlFor="lv">미리보기</label>
      <select id="lv" value={level} onChange={(e) => pick(Number(e.target.value))}>
        {LEVELS.map((l) => (
          <option key={l.level} value={l.level}>
            레벨 {l.level} · {l.name}
          </option>
        ))}
      </select>
      <span className="micro">학습량에 따라 화면이 열리는 방식 확인용 · 배포 전 제거</span>
    </div>
  );
}
