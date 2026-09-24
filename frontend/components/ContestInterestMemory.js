'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  clearContestInterests,
  saveContestInterests,
  useContestInterestMemory,
} from '@/lib/contest-interest-memory';
import styles from './ContestInterestMemory.module.css';

export default function ContestInterestMemory({ draftKeywords, onApply, disabled = false }) {
  const { memory, ready, status } = useContestInterestMemory();
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const canSave = typeof draftKeywords === 'string';

  function update(action) {
    setFeedback('');
    setError('');
    try {
      action();
    } catch (err) {
      setError(err.message);
    }
  }

  function save() {
    update(() => {
      const keywords = saveContestInterests(draftKeywords);
      onApply?.(keywords.join(', '));
      setFeedback('이 브라우저에 저장했습니다. 다음 방문부터 이 키워드로 추천합니다.');
    });
  }

  function remove(keyword) {
    update(() => {
      const remaining = keyword ? memory.keywords.filter((term) => term !== keyword) : [];
      if (remaining.length) saveContestInterests(remaining.join(', '));
      else clearContestInterests();
      onApply?.(remaining.join(', '));
      setFeedback(keyword ? `‘${keyword}’ 키워드를 삭제했습니다.` : '저장된 관심 키워드를 모두 삭제했습니다.');
    });
  }

  return (
    <section className={styles.memory} aria-labelledby="contest-memory-title">
      <h2 id="contest-memory-title" className={styles.title}>저장된 관심 키워드 · 실습</h2>
      <p className="hint">
        이 브라우저에만 저장됩니다. 같은 브라우저를 쓰는 사람도 볼 수 있으며, 계정이나 다른 기기와 동기화되지 않습니다.
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
          <button className="btn btn-sm" type="button" disabled={!ready || disabled || !draftKeywords.trim()} onClick={save}>
            이 브라우저에 저장
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
