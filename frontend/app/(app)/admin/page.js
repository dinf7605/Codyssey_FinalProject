'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import SectionTitle from '@/components/SectionTitle';
import { api, getToken } from '@/lib/api';

const SOURCE_LABELS = {
  agent: 'AI 에이전트',
  partial: '부분 처리',
  template: '템플릿 대체',
};

function formatTime(value) {
  return new Date(value).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour12: false,
  });
}

export default function AdminPage() {
  const [day, setDay] = useState('');
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState(null);
  const requestKey = `${day}:${page}:${revision}`;
  const loading = result?.key !== requestKey;
  const data = loading ? null : result?.data;
  const error = loading ? null : result?.error;

  useEffect(() => {
    let active = true;

    Promise.resolve()
      .then(() => {
        if (!getToken()) {
          const error = new Error('로그인이 필요합니다.');
          error.status = 401;
          throw error;
        }
        return api.admin.logs({ day, page });
      })
      .then((data) => {
        if (active) setResult({ key: requestKey, data });
      })
      .catch((error) => {
        if (!active) return;
        const message = error.status === 401
          ? '로그인이 필요하거나 로그인 시간이 만료되었습니다.'
          : error.status === 403
            ? '관리자 권한이 있는 계정만 이용할 수 있습니다.'
            : '처리 기록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';
        setResult({
          key: requestKey,
          error: { status: error.status, message },
        });
      });

    return () => { active = false; };
  }, [day, page, requestKey]);

  function changeDay(event) {
    setDay(event.target.value);
    setPage(1);
  }

  function refresh() {
    setRevision((value) => value + 1);
  }

  const totalPages = data
    ? Math.max(1, Math.ceil(data.total / data.page_size))
    : 1;

  return (
    <>
      <header className="stack" style={{ gap: 6 }}>
        <h1 style={{ fontSize: 20 }}>관리자</h1>
        <p className="muted tiny">AI 처리 기록 · 한국 시간 기준</p>
      </header>

      {loading && <p role="status">권한 및 처리 기록을 확인하고 있습니다.</p>}

      {error && (
        <section className="sec">
          <p role="alert">{error.message}</p>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {error.status === 401 && <Link href="/login">로그인</Link>}
            <Link href="/mypage">내 계정으로 이동</Link>
            <button type="button" className="btn btn-sm" onClick={refresh}>
              다시 확인
            </button>
          </div>
        </section>
      )}

      {data && (
        <>
          <section className="sec">
            <SectionTitle>AI 처리 기록</SectionTitle>

            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <label htmlFor="admin-log-day">조회 날짜</label>
              <input
                id="admin-log-day"
                type="date"
                min="2000-01-01"
                max="9998-12-31"
                value={day || data.day}
                onChange={changeDay}
              />
              <button type="button" className="btn btn-sm" onClick={refresh}>
                새로고침
              </button>
            </div>

            <p className="hint">
              {data.day} · 전체 처리 기록 {data.total}건
            </p>
            <p className="hint">
              템플릿 대체 처리도 포함됩니다. 처리 기록 수는 실제 AI 호출 횟수와 다를 수 있습니다.
              비용과 실패율은 아직 집계되지 않습니다.
            </p>

            {data.items.length === 0 ? (
              <p>조회된 처리 기록이 없습니다.</p>
            ) : (
              <div className="rows">
                {data.items.map((item) => (
                  <div className="row" key={item.id}>
                    <div className="row-main">
                      <b>{item.feature === 'plan.decompose' ? '학습 분해' : item.feature}</b>
                      <span>
                        {formatTime(item.created_at)} · {SOURCE_LABELS[item.source] || item.source || '출처 미기록'}
                      </span>
                      <span>
                        모델: {item.model || '미기록'} · 도구 호출: {item.tool_calls}회
                        {' · '}처리 시간: {item.latency_ms == null ? '미기록' : `${item.latency_ms}ms`}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <nav aria-label="처리 기록 페이지" style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 16 }}>
              <button
                type="button"
                className="btn btn-sm"
                disabled={page <= 1}
                onClick={() => { setDay(data.day); setPage(page - 1); }}
              >
                이전
              </button>
              <span>{page} / {totalPages}</span>
              <button
                type="button"
                className="btn btn-sm"
                disabled={page >= totalPages || page >= 10000}
                onClick={() => { setDay(data.day); setPage(page + 1); }}
              >
                다음
              </button>
            </nav>
          </section>

          <section className="sec">
            <SectionTitle>수집 공고 점검</SectionTitle>
            <p className="hint">공고 점검 기능을 준비하고 있습니다.</p>
          </section>
        </>
      )}
    </>
  );
}
