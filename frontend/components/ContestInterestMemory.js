'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  clearContestInterests,
  saveContestInterests,
  useContestInterestMemory,
} from '@/lib/contest-interest-memory';
import styles from './ContestInterestMemory.module.css';
import { api } from '@/lib/api';
import { useAuthToken } from '@/lib/auth-token';
import { normalizeInterestKeywords } from '@/lib/contest-interest-memory';

export default function ContestInterestMemory({ draftKeywords, onApply, disabled = false }) {
  const { memory: browserMemory, ready: browserReady, status: browserStatus } = useContestInterestMemory();
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const token = useAuthToken();
  const account = Boolean(token);
  const [accountState, setAccountState] = useState(null);
  const accountMemory = accountState?.owner === token ? accountState.row : undefined;
  const [busy, setBusy] = useState(false);
  const canSave = typeof draftKeywords === 'string';

  useEffect(() => {
    if (!token) return;
    let alive = true;
    api.memories.list().then((rows) => {
      if (alive) {
        const row = rows.find((item) => item.memory_type === 'interest_tags');
        setAccountState({ owner: token, row: row || null });
      }
    }).catch((err) => {
      if (alive) { setError(err.message); setAccountState({ owner: token, row: null }); }
    });
    return () => { alive = false; };
  }, [token]);

  const memory = account ? (accountMemory ? {
    keywords: accountMemory.value.tags || [], updatedAt: accountMemory.updated_at,
  } : null) : browserMemory;
  const ready = browserReady && (!account || accountMemory !== undefined);
  const status = account ? 'ok' : browserStatus;

  async function save() {
    setFeedback(''); setError(''); setBusy(true);
    try {
      const keywords = normalizeInterestKeywords(draftKeywords);
      if (!keywords.length) throw new Error('저장할 관심 키워드를 먼저 입력해 주세요.');
      if (account) {
        const row = await api.memories.saveInterests(keywords);
        setAccountState({ owner: token, row });
      } else {
        saveContestInterests(draftKeywords);
      }
      onApply?.(keywords.join(', '));
      setFeedback(account ? '계정에 관심 분야를 저장했습니다.' : '이 브라우저에 저장했습니다.');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function remove(keyword) {
    setFeedback(''); setError(''); setBusy(true);
    try {
      const remaining = keyword ? memory.keywords.filter((term) => term !== keyword) : [];
      if (account) {
        if (remaining.length) setAccountState({ owner: token, row: await api.memories.saveInterests(remaining) });
        else if (accountMemory) { await api.memories.remove(accountMemory.id); setAccountState({ owner: token, row: null }); }
      } else if (remaining.length) saveContestInterests(remaining.join(', '));
      else clearContestInterests();
      onApply?.(remaining.join(', '));
      setFeedback(keyword ? `‘${keyword}’ 키워드를 삭제했습니다.` : '저장된 관심 키워드를 모두 삭제했습니다.');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <section className={styles.memory} aria-labelledby="contest-memory-title">
      <h2 id="contest-memory-title" className={styles.title}>저장된 관심 키워드</h2>
      <p className="hint">
        {account ? '로그인한 계정에 저장되며 마이페이지에서 삭제할 수 있습니다.' : '이 브라우저에만 저장됩니다. 로그인하면 계정에 저장할 수 있습니다.'}
      </p>
      {!ready ? <p className="tiny muted">저장 정보를 확인하고 있습니다.</p> : memory ? (
        <>
          <ul className={styles.keywords} aria-label="저장된 관심 키워드">
            {memory.keywords.map((keyword) => (
              <li key={keyword}>
                <span>{keyword}</span>
                <button type="button" aria-label={`저장 키워드 ${keyword} 삭제`} disabled={disabled} onClick={() => remove(keyword)}>
                  삭제
                </button>
              </li>
            ))}
          </ul>
          <p className="hint">
            근거: 사용자가 직접 저장 · 갱신: {new Date(memory.updatedAt).toLocaleString('ko-KR')}
          </p>
        </>
      ) : (
        <p className="tiny muted">저장된 관심 키워드가 없습니다.</p>
      )}
      {status !== 'ok' && (
        <p className="hint hint-error" role="alert">
          {status === 'unavailable'
            ? '브라우저 저장소를 사용할 수 없습니다. 키워드 검색은 계속 사용할 수 있습니다.'
            : '저장 정보를 읽을 수 없습니다. 새 키워드로 저장하거나 저장 정보를 삭제해 주세요.'}
        </p>
      )}
      <div className={styles.actions}>
        {canSave ? (
          <button className="btn btn-sm" type="button" disabled={!ready || disabled || busy || !draftKeywords.trim()} onClick={save}>
            {account ? '내 계정에 저장' : '이 브라우저에 저장'}
          </button>
        ) : (
          <Link className="btn btn-sm" href="/contests">공모전에서 키워드 편집</Link>
        )}
        {memory && onApply && (
          <button className="btn btn-sm" type="button" disabled={disabled} onClick={() => onApply(memory.keywords.join(', '))}>
            저장한 키워드로 추천
          </button>
        )}
        {(memory || status === 'invalid') && (
          <button className="btn btn-sm" type="button" disabled={disabled} onClick={() => remove()}>
            저장 키워드 전체 삭제
          </button>
        )}
      </div>
      {feedback && <p className="hint" role="status">{feedback}</p>}
      {error && <p className="hint hint-error" role="alert">{error}</p>}
    </section>
  );
}
