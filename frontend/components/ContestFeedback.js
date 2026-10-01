'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { useAuthToken } from '@/lib/auth-token';

export default function ContestFeedback({ contestId }) {
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState('field');
  const token = useAuthToken();
  if (!token) return null;

  async function send(rating) {
    setBusy(true);
    setMessage('');
    try {
      await api.contests.feedback(contestId, rating, rating === 'not_relevant' ? reason : null);
      setMessage(rating === 'helpful' ? '도움됨으로 저장했습니다.' : '안 맞음으로 저장했습니다. 다음 추천에서 제외합니다.');
    } catch (error) {
      setMessage(error.message || '평가를 저장하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: 4 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={() => send('helpful')}>도움됨</button>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={() => send('not_relevant')}>안 맞음</button>
      </div>
      <label className="tiny muted">
        안 맞는 이유{' '}
        <select value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)}>
          <option value="field">관심 분야</option>
          <option value="difficulty">난이도</option>
          <option value="deadline">기한</option>
        </select>
      </label>
      {message && <span className="tiny muted" role="status">{message}</span>}
    </div>
  );
}
