'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

const INDEX_LABELS = {
  pending: '색인 대기',
  indexed: '색인 완료',
  failed: '색인 실패',
  missing: '색인 기록 없음',
};

const STATUS_LABELS = {
  upcoming: '접수 예정',
  open: '접수 중',
  closed: '마감',
  unknown: '상태 미확인',
};

function formatTime(value) {
  return new Date(value).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour12: false,
  });
}

export default function AdminContestInspection() {
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState(null);
  const requestKey = `${page}:${revision}`;
  const loading = result?.key !== requestKey;
  const data = loading ? null : result?.data;
  const error = loading ? null : result?.error;

  useEffect(() => {
    let active = true;

    api.admin.contestInspection({ page, pageSize: 20 })
      .then((data) => {
        if (active) setResult({ key: requestKey, data });
      })
      .catch((error) => {
        if (!active) return;
        const message = error.status === 401
          ? '로그인이 필요하거나 로그인 시간이 만료되었습니다.'
          : error.status === 403
            ? '관리자 권한이 있는 계정만 이용할 수 있습니다.'
            : '공고 점검 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';
        setResult({
          key: requestKey,
          error: { status: error.status, message },
        });
      });

    return () => { active = false; };
  }, [page, requestKey]);

  function refresh() {
    setRevision((value) => value + 1);
  }

  const totalPages = data
    ? Math.max(1, Math.ceil(data.total / data.page_size))
    : 1;

  return (
    <div>
      <p className="hint">
        마감 공고를 포함한 저장된 공고입니다. 수집 시각은 한국 시간 기준입니다.
      </p>

      <button
        type="button"
        className="btn btn-sm"
        onClick={refresh}
        disabled={loading}
      >
        새로고침
      </button>

      {loading && <p role="status">공고 점검 정보를 불러오고 있습니다.</p>}

      {error && (
        <div>
          <p role="alert">{error.message}</p>
          {error.status === 401 && <Link href="/login">로그인</Link>}
        </div>
      )}

      {data && (
        <>
          <p className="hint">전체 저장 공고 {data.total}건</p>

          {data.items.length === 0 ? (
            <p>
              {data.total === 0
                ? '저장된 공고가 없습니다.'
                : '현재 페이지에 공고가 없습니다. 이전 페이지로 이동해 주세요.'}
            </p>
          ) : (
            <div className="rows">
              {data.items.map((item) => (
                <div className="row" key={item.id}>
                  <div className="row-main">
                    <b>{item.title}</b>
                    <span>{item.host ? `주최: ${item.host} · ` : ''}수집처: {item.source}</span>
                    <span>
                      마감일: {item.deadline || '원문 확인'} · {STATUS_LABELS[item.status] || '상태 미확인'}
                    </span>
                    <span>수집: {formatTime(item.collected_at)}</span>
                    <span>
                      {INDEX_LABELS[item.index_status] || '색인 상태 미확인'}
                      {item.indexed_at ? ` · 색인 시각: ${formatTime(item.indexed_at)}` : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          <nav
            aria-label="공고 목록 페이지"
            style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 16 }}
          >
            <button
              type="button"
              className="btn btn-sm"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              이전
            </button>
            <span>{page} / {totalPages}</span>
            <button
              type="button"
              className="btn btn-sm"
              disabled={page >= totalPages || page >= 10000}
              onClick={() => setPage((value) => value + 1)}
            >
              다음
            </button>
          </nav>
        </>
      )}

      <p className="hint" style={{ marginTop: 16 }}>
        색인 기록 없음은 색인 상태 행이 없다는 뜻입니다.
        수집 중 제외된 공고와 중복 의심 공고는 아직 집계하지 않습니다.
      </p>
    </div>
  );
}
