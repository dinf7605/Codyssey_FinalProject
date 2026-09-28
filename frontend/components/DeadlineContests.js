'use client';

import { useEffect, useState } from 'react';
import ContestCard from './ContestCard';
import EmptyState from './EmptyState';
import { api } from '@/lib/api';
import { daysLeft } from '@/lib/contests';

// 대시보드의 공모전 카드 — 위비티에서 모은 실제 공고 중 마감이 가까운 것 (담당 D 데이터, FR-CONT-03)
// 개인화 추천(FR-CONT-04)이 생기기 전까지는 마감 임박순이다. AI 가 고른 것이 아니므로 AI 표시를 하지 않는다.

export default function DeadlineContests({ limit = 2 }) {
  const [state, setState] = useState({ status: 'loading', items: [] });

  useEffect(() => {
    let alive = true;
    api.contests.search({ limit }).then(
      (res) => alive && setState({ status: 'ready', items: res.items }),
      () => alive && setState({ status: 'error', items: [] }),
    );
    return () => { alive = false; };
  }, [limit]);

  if (state.status === 'loading') return <p className="hint">공모전을 불러오는 중…</p>;
  if (state.status === 'error') return <p className="hint">공모전을 불러오지 못했어요.</p>;
  if (!state.items.length) return <EmptyState title="지금 접수 중인 공모전이 없습니다" />;

  return (
    <ul className="list">
      {state.items.map((c) => (
        <ContestCard
          key={c.id}
          contest={{ id: c.id, title: c.title, host: c.host, deadline: c.deadline, dDay: daysLeft(c.deadline), field: c.fields[0] || '' }}
        />
      ))}
    </ul>
  );
}
