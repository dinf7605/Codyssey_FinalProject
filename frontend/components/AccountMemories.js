'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useAuthToken } from '@/lib/auth-token';
import { clearContestInterests } from '@/lib/contest-interest-memory';
import SectionTitle from '@/components/SectionTitle';

const LABELS = {
  preferred_study_time: '선호 학습 시간대',
  effort_deviation: '예상·실제 학습시간 차이',
  interest_tags: '관심 분야',
  rejected_recommendations: '맞지 않았던 추천',
  four_week_completion_rate: '최근 4주 완료율',
};

function describe(row) {
  if (row.memory_type === 'interest_tags') return (row.value.tags || []).join(', ');
  if (row.memory_type === 'rejected_recommendations') return '공모전 추천 거절 이력 · 영향은 4주마다 절반으로 줄어듭니다.';
  if (row.memory_type === 'preferred_study_time') return `${row.value.band || '확인 중'} · 최근 ${row.value.session_count || 0}회 학습 기준`;
  if (row.memory_type === 'effort_deviation') return `예상 대비 평균 ${row.value.percent > 0 ? '+' : ''}${row.value.percent ?? 0}% · ${row.value.session_count || 0}회 기준`;
  if (row.memory_type === 'four_week_completion_rate') return `최근 4주 계획 블록 ${row.value.completed || 0}/${row.value.planned || 0}개 완료 · ${row.value.percent ?? 0}%`;
  return JSON.stringify(row.value);
}

export default function AccountMemories() {
  const [loaded, setLoaded] = useState(null);
  const [message, setMessage] = useState('');
  const token = useAuthToken();
  const signedIn = Boolean(token);
  const rows = loaded?.owner === token ? loaded.rows : null;

  useEffect(() => {
    if (token) api.memories.list().then((result) => setLoaded({ owner: token, rows: result })).catch((err) => {
      setLoaded({ owner: token, rows: [] });
      setMessage(err.message);
    });
  }, [token]);

  async function remove(id) {
    try {
      await api.memories.remove(id);
      if (rows?.find((row) => row.id === id)?.memory_type === 'interest_tags') {
        try { clearContestInterests(); } catch { /* 서버 삭제는 이미 완료됨 */ }
      }
      setLoaded((previous) => ({ owner: token, rows: previous.rows.filter((row) => row.id !== id) }));
      setMessage('저장된 정보를 삭제했습니다.');
    } catch (err) { setMessage(err.message); }
  }

  async function clear() {
    try {
      await api.memories.clear();
      try { clearContestInterests(); } catch { /* 서버 삭제는 이미 완료됨 */ }
      setLoaded({ owner: token, rows: [] });
      setMessage('저장된 정보를 모두 삭제했습니다.');
    } catch (err) { setMessage(err.message); }
  }

  function confirmDelete(id, label) {
    if (!window.confirm(`${label}을(를) 삭제할까요? 삭제한 정보는 복구할 수 없습니다. 새 학습 기록을 저장하면 학습 통계는 다시 계산될 수 있습니다.`)) return;
    if (id) remove(id);
    else clear();
  }

  return (
    <section className="sec">
      <SectionTitle>저장된 학습 정보</SectionTitle>
      {!signedIn ? <p className="hint">로그인하면 계정에 저장된 정보를 볼 수 있습니다.</p> :
        rows === null ? <p className="hint">저장 정보를 불러오는 중…</p> :
        rows.length === 0 ? <p className="hint">저장된 학습 정보가 없습니다.</p> : (
          <>
            <div className="rows">
              {rows.map((row) => (
                <div className="row" key={row.id}>
                  <div className="row-main">
                    <b>{LABELS[row.memory_type] || row.memory_type}</b>
                    <span>{describe(row)}</span>
                    <span className="dim micro">근거: {row.basis}</span>
                    <span className="dim micro">갱신: {new Date(row.updated_at).toLocaleString('ko-KR')}</span>
                  </div>
                  <button type="button" className="btn btn-sm" onClick={() => confirmDelete(row.id, LABELS[row.memory_type] || row.memory_type)}>삭제</button>
                </div>
              ))}
            </div>
            <button type="button" className="btn btn-sm" onClick={() => confirmDelete(null, '모든 저장 정보')}>저장 정보 전체 삭제</button>
          </>
        )}
      {message && <p className="hint" role="status">{message}</p>}
    </section>
  );
}
