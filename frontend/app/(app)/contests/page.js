'use client';

import { useState } from 'react';
import ContestCard from '@/components/ContestCard';
import EmptyState from '@/components/EmptyState';
import { AiNotice } from '@/components/AiNotice';
import { contests } from '@/lib/mock';

// FR-CONT-03 검색·필터 / FR-CONT-04 추천 / FR-CONT-05 추천 이유
// 비회원도 검색·상세 조회까지 사용할 수 있다.

const FIELDS = ['전체', 'IT·개발', 'IT·데이터', '디자인', '마케팅', '기획'];

export default function ContestsPage() {
  const [field, setField] = useState('전체');
  const [query, setQuery] = useState('');

  const list = contests.filter((c) => {
    const byField = field === '전체' || c.field === field;
    const byQuery = !query || c.title.includes(query) || c.host.includes(query);
    return byField && byQuery;
  });

  return (
    <>
      <header className="stack" style={{ gap: 4 }}>
        <h1 style={{ fontSize: 20 }}>공모전</h1>
        <p className="muted tiny">매일 새벽 5시에 새 공고를 모읍니다</p>
      </header>

      <div className="field">
        <input
          className="input"
          type="search"
          aria-label="공모전 검색"
          placeholder="공모전 이름이나 주최기관 검색"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="scroller">
        {FIELDS.map((f) => (
          <button
            key={f}
            type="button"
            className="chip"
            aria-pressed={field === f}
            onClick={() => setField(f)}
          >
            {f}
          </button>
        ))}
      </div>

      {list.length === 0 ? (
        <EmptyState
          title="조건에 맞는 공모전이 없습니다"
          description="분야 필터를 넓히거나 검색어를 지워 보세요."
          action={
            <button
              className="btn btn-sm"
              onClick={() => {
                setField('전체');
                setQuery('');
              }}
            >
              필터 초기화
            </button>
          }
        />
      ) : (
        <>
          <ul className="list">
            {list.map((c) => (
              <ContestCard key={c.id} contest={c} />
            ))}
          </ul>
          <AiNotice />
        </>
      )}
    </>
  );
}
