'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';

// 관리자 DB 현황 (읽기 전용) — 백엔드 services/admin_db.py
// 테이블마다 행 수와 마지막 기록 시각을 보여 주고, 누르면 최근 행을 펼친다.
// Supabase 대시보드 없이 "기록이 쌓이는지" 확인하려는 용도다. 수정·삭제는 없다.
// 이메일·닉네임·사용자 id·사용자가 쓴 글은 서버에서 이미 가려져 온다.

const PAGE_SIZE = 10;

function when(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul', hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function cell(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? '예' : '아니오';
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  const text = String(value);
  return /^\d{4}-\d{2}-\d{2}T/.test(text) ? when(text) : text;
}

function TableRows({ name }) {
  const [page, setPage] = useState(1);
  const [state, setState] = useState({ key: null, data: null, error: '' });
  const key = `${name}:${page}`;

  useEffect(() => {
    let alive = true;
    api.admin.dbTable(name, { page, pageSize: PAGE_SIZE }).then(
      (data) => alive && setState({ key, data, error: '' }),
      (err) => alive && setState({ key, data: null, error: err.message || '행을 불러오지 못했습니다.' }),
    );
    return () => { alive = false; };
  }, [name, page, key]);

  if (state.key !== key) return <p className="hint" role="status">행을 불러오는 중…</p>;
  if (state.error) return <p className="hint hint-error" role="alert">{state.error}</p>;
  const { data } = state;
  if (!data.rows.length) return <p className="hint">아직 행이 없습니다.</p>;
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="db-scroll" tabIndex={0} aria-label={`${data.label} 최근 행`}>
        <table className="db-table">
          <thead>
            <tr>{data.columns.map((c) => <th key={c} scope="col">{c}{data.masked.includes(c) ? ' *' : ''}</th>)}</tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <tr key={i}>{data.columns.map((c) => <td key={c}>{cell(row[c])}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>이전</button>
        <span className="tiny">{page} / {pages}</span>
        <button type="button" className="btn btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>다음</button>
        {data.masked.length > 0 && <span className="dim tiny">* 개인정보 보호로 줄여서 보여 줍니다</span>}
      </div>
    </div>
  );
}

export default function AdminDbStatus() {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState({ revision: -1, tables: null, error: '' });
  const [open, setOpen] = useState(null);

  const refresh = useCallback(() => setRevision((r) => r + 1), []);

  useEffect(() => {
    let alive = true;
    api.admin.dbTables().then(
      (res) => alive && setState({ revision, tables: res.tables, error: '' }),
      (err) => alive && setState({ revision, tables: null, error: err.message || 'DB 현황을 불러오지 못했습니다.' }),
    );
    return () => { alive = false; };
  }, [revision]);

  const loading = state.revision !== revision;

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <p className="hint" style={{ margin: 0 }}>행 수가 늘어나면 기록이 쌓이고 있는 것입니다. 읽기 전용입니다.</p>
        <button type="button" className="btn btn-sm" onClick={refresh} disabled={loading}>새로고침</button>
      </div>
      {loading && <p className="hint" role="status">DB 현황을 확인하고 있습니다.</p>}
      {!loading && state.error && <p className="hint hint-error" role="alert">{state.error}</p>}
      {!loading && state.tables && (
        <ul className="rows" aria-label="테이블 목록">
          {state.tables.map((t) => (
            <li key={t.name} className="stack" style={{ gap: 8 }}>
              <button
                type="button"
                className="row db-row"
                aria-expanded={open === t.name}
                onClick={() => setOpen(open === t.name ? null : t.name)}
              >
                <span className="row-main">
                  <b>{t.label}</b>
                  <span className="dim tiny">{t.name} · 담당 {t.owner}</span>
                </span>
                <span className="db-count">
                  {t.error ? <span className="pill pill-late">조회 실패</span> : (
                    <>
                      <b className="mono">{t.rows.toLocaleString('ko-KR')}행</b>
                      <span className="dim tiny">마지막 {when(t.latest_at)}</span>
                    </>
                  )}
                </span>
              </button>
              {open === t.name && !t.error && <TableRows name={t.name} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
