'use client';

import { useEffect } from 'react';
import { densityForLevel } from '@/lib/ui';
import { useStats } from '@/lib/useStats';

// FR-UI-01 / FR-UI-02 — 누적 학습시간이 레벨을, 레벨이 테마와 밀도를 정한다.
//
// 레벨은 로그인한 사용자의 기록(/study/stats)으로만 정해진다. 서버는 그 값을 모르므로
// 루트 레이아웃은 레벨 1로 그리고, 여기서 실제 레벨을 <html> 에 붙인다.
// 매번 레벨 1 화면이 번쩍이지 않게 마지막으로 본 레벨을 브라우저에 기억해 두고 먼저 적용한다.

const KEY = 'sp_level';

function apply(level) {
  const root = document.documentElement;
  root.dataset.level = String(level);
  root.dataset.density = densityForLevel(level);
}

export default function AdaptiveTheme() {
  const { status, data } = useStats();

  useEffect(() => {
    try {
      const cached = Number(window.localStorage.getItem(KEY));
      if (cached >= 1 && cached <= 5) apply(cached);
    } catch {
      // 저장소가 막혀 있으면 기억 없이 간다
    }
  }, []);

  useEffect(() => {
    if (status === 'ready' && data) {
      apply(data.level);
      try {
        window.localStorage.setItem(KEY, String(data.level));
      } catch {
        // 무시
      }
    } else if (status === 'anon') {
      apply(1);
      try {
        window.localStorage.removeItem(KEY);
      } catch {
        // 무시
      }
    }
  }, [status, data]);

  return null;
}
