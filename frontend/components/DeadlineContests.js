'use client';

import { useEffect, useState } from 'react';
import ContestCard from './ContestCard';
import EmptyState from './EmptyState';
import { api } from '@/lib/api';
import { getToken } from '@/lib/api';
import { daysLeft } from '@/lib/contests';

// 대시보드 공고 카드. 위비티 링크 전용 행은 마감일을 알 수 없다.

export default function DeadlineContests({ limit = 2 }) {
  const [state, setState] = useState({ status: 'loading', items: [] });

  useEffect(() => {
    let alive = true;
    const signedIn = Boolean(getToken());
    const fetch = signedIn ? api.contests.recommend() : api.contests.search({ limit });
    fetch.then(
      (res) => alive && setState({
        status: 'ready',
        items: signedIn ? res.items.slice(0, limit).map((item) => ({
          ...item.contest, reason: item.reason, aiGenerated: res.method === 'title_claude',
        })) : res.items,
        personalized: signedIn,
      }),
      () => alive && setState({ status: 'error', items: [] }),
    );
    return () => { alive = false; };
  }, [limit]);

  if (state.status === 'loading') return <p className="hint">공모전을 불러오는 중…</p>;
  if (state.status === 'error') return <p className="hint">공모전을 불러오지 못했어요.</p>;
  if (!state.items.length) return <EmptyState
    title={state.personalized ? '이번 주 추천 공모전이 없습니다' : '지금 접수 중인 공모전이 없습니다'}
    description={state.personalized ? '공모전 화면에서 관심 키워드를 저장하거나 다른 키워드로 찾아보세요.' : undefined}
  />;

  return (
    <ul className="list">
      {state.items.map((c) => (
        <ContestCard
          key={c.id}
          contest={{ id: c.id, title: c.title, host: c.host, deadline: c.deadline,
            dDay: daysLeft(c.deadline), field: c.fields[0] || '', source: c.source,
            reason: c.reason, aiGenerated: c.aiGenerated, recommended: state.personalized }}
        />
      ))}
    </ul>
  );
}
