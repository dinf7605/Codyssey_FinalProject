'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

// FR-ADMIN-01 수집 공고 고치기 — 관리자 화면 '수집 공고 점검' 목록의 한 줄에서 연다.
// 바꾼 칸만 보낸다 (PATCH /admin/contests/{id}). 저장하면 목록을 새로 읽는다.

const STATUS = [
  ['open', '접수 중'], ['upcoming', '접수 예정'], ['closed', '마감'], ['unknown', '상태 미확인'],
];

export default function AdminContestFix({ item, onSaved, onCancel }) {
  const [form, setForm] = useState({
    title: item.title, host: item.host || '', deadline: item.deadline || '', status: item.status, fields: '',
  });
  const [state, setState] = useState({ pending: false, error: '' });

  async function save(event) {
    event.preventDefault();
    const changes = {};
    if (form.title.trim() !== item.title) changes.title = form.title;
    if (form.host.trim() !== (item.host || '')) changes.host = form.host;
    if (form.deadline && form.deadline !== item.deadline) changes.deadline = form.deadline;
    if (form.status !== item.status) changes.status = form.status;
    if (form.fields.trim()) changes.fields = form.fields.split(',').map((v) => v.trim()).filter(Boolean);
    if (!Object.keys(changes).length) {
      setState({ pending: false, error: '바뀐 칸이 없습니다.' });
      return;
    }
    setState({ pending: true, error: '' });
    try {
      await api.admin.fixContest(item.id, changes);
      onSaved();
    } catch (err) {
      setState({ pending: false, error: err.message || '고치지 못했습니다.' });
    }
  }

  const set = (key) => (event) => setForm((old) => ({ ...old, [key]: event.target.value }));

  return (
    <form className="panel stack" style={{ gap: 8, padding: 'var(--gap-3)', marginTop: 8 }} onSubmit={save}
      aria-label={`${item.title} 고치기`}>
      <div className="field">
        <label htmlFor={`fix-title-${item.id}`}>제목</label>
        <input id={`fix-title-${item.id}`} className="input" value={form.title} maxLength={200} onChange={set('title')} required />
      </div>
      <div className="field">
        <label htmlFor={`fix-host-${item.id}`}>주최</label>
        <input id={`fix-host-${item.id}`} className="input" value={form.host} maxLength={100} onChange={set('host')} />
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <div className="field">
          <label htmlFor={`fix-deadline-${item.id}`}>마감일</label>
          <input id={`fix-deadline-${item.id}`} type="date" className="input" value={form.deadline} onChange={set('deadline')} />
        </div>
        <div className="field">
          <label htmlFor={`fix-status-${item.id}`}>상태</label>
          <select id={`fix-status-${item.id}`} className="input" value={form.status} onChange={set('status')}>
            {STATUS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor={`fix-fields-${item.id}`}>분야 (바꿀 때만, 쉼표로 구분)</label>
        <input id={`fix-fields-${item.id}`} className="input" value={form.fields} placeholder="예: 웹/모바일/IT, 과학/공학"
          onChange={set('fields')} />
      </div>
      {state.error && <p className="hint hint-error" role="alert">{state.error}</p>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="submit" className="btn btn-sm btn-primary" disabled={state.pending}>{state.pending ? '저장 중…' : '저장'}</button>
        <button type="button" className="btn btn-sm btn-quiet" onClick={onCancel} disabled={state.pending}>취소</button>
      </div>
    </form>
  );
}
