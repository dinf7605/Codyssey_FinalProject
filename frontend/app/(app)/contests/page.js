'use client';

import { useEffect, useState } from 'react';
import EmptyState from '@/components/EmptyState';
import api from '@/lib/api';
import ContestInterestMemory from '@/components/ContestInterestMemory';
import { useContestInterestMemory } from '@/lib/contest-interest-memory';
import styles from './contests.module.css';

const SUGGESTIONS = ['AI', '데이터', '웹', '디자인', '환경'];

function originalUrl(contest) {
  if (contest.is_demo || !contest.source_url) return null;
  try {
    const url = new URL(contest.source_url);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export default function ContestsPage() {
  const [input, setInput] = useState(null);
  const [request, setRequest] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const { memory, ready } = useContestInterestMemory();
  const savedKeywords = memory?.keywords.join(', ') || '';
  const inputValue = input ?? savedKeywords;
  const activeKeywords = request?.keywords ?? savedKeywords;

  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    api.contests.demoList(activeKeywords, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) {
          setResult(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(
          err instanceof TypeError
            ? '공모전 정보를 불러오지 못했습니다. 연결 상태를 확인하고 다시 시도해 주세요.'
            : err.message || '공모전 정보를 불러오지 못했습니다.'
        );
        setLoading(false);
      });
    return () => controller.abort();
  }, [request, activeKeywords, ready]);

  function load(keywords) {
    setInput(keywords);
    setLoading(true);
    setError('');
    setResult(null);
    setRequest({ keywords });
  }

  const recommended = Boolean(result?.keywords.length);

  return (
    <>
      <header className="stack" style={{ gap: 6 }}>
        <p className={styles.eyebrow}>관심에서 시작하는 도전</p>
        <h1 style={{ fontSize: 26 }}>공모전 탐색</h1>
        <p className="muted">관심 있는 주제로 공모전을 찾아보세요.</p>
      </header>

      <aside className={styles.notice} aria-label="테스트 데이터 안내">
        <strong>테스트 데이터로 체험 중</strong>
        <p>직접 만든 가상 공모전 20개입니다. 실제 모집 공고가 아니며 원문 링크는 제공하지 않습니다.</p>
      </aside>

      <section className={styles.searchPanel} aria-labelledby="interest-heading">
        <h2 id="interest-heading" className={styles.sectionTitle}>어떤 주제에 관심이 있나요?</h2>
        <form onSubmit={(event) => { event.preventDefault(); load(inputValue.trim()); }}>
          <div className="field">
            <label htmlFor="contest-interests">관심 키워드</label>
            <div className={styles.searchRow}>
              <input
                id="contest-interests"
                className="input"
                type="search"
                value={inputValue}
                maxLength={200}
                placeholder="예: AI, 데이터"
                aria-describedby="contest-interest-help"
                onChange={(event) => setInput(event.target.value)}
              />
              <button className="btn btn-primary" type="submit" disabled={loading}>
                {loading ? '불러오는 중…' : '추천받기'}
              </button>
            </div>
            <p id="contest-interest-help" className="hint">
              여러 키워드는 쉼표로 구분하세요. 제목에 일치하는 키워드가 많은 순서로 추천합니다.
            </p>
          </div>
        </form>
        <div className={styles.suggestions} aria-label="추천 키워드">
          {SUGGESTIONS.map((keyword) => (
            <button
              className="chip"
              type="button"
              key={keyword}
              disabled={loading}
              aria-pressed={activeKeywords === keyword}
              onClick={() => load(keyword)}
            >
              {keyword}
            </button>
          ))}
          <button className="btn btn-sm" type="button" disabled={loading} onClick={() => load('')}>
            전체 보기
          </button>
        </div>
      </section>

      <ContestInterestMemory draftKeywords={inputValue} onApply={load} disabled={loading} />

      <section className={styles.results} aria-labelledby="contest-results-heading" aria-busy={loading}>
        <div className="sec-head">
          <h2 id="contest-results-heading" className={styles.sectionTitle}>
            {recommended ? '관심 키워드 추천' : '공모전 목록'}
          </h2>
          <span className="muted" role="status" aria-live="polite">
            {loading ? '불러오는 중' : error ? '연결 확인 필요' : `${result?.total ?? 0}개`}
          </span>
        </div>

        {loading && <p className={styles.loading}>공모전을 불러오고 있습니다.</p>}
        {error && (
          <div role="alert">
            <EmptyState
              title="목록을 불러오지 못했습니다"
              description={error}
              action={
                <button className="btn btn-sm" type="button" onClick={() => load(activeKeywords)}>
                  다시 시도
                </button>
              }
            />
          </div>
        )}

        {!loading && !error && result && (
          <>
            {recommended && (
              <p className="muted tiny">
                적용한 키워드: {result.keywords.join(', ')} · 제목 기준 추천
              </p>
            )}
            {result.items.length === 0 ? (
              <EmptyState
                title="일치하는 공모전이 없습니다"
                description="다른 키워드를 입력하거나 전체 공모전을 확인해 보세요."
                action={
                  <button className="btn btn-sm" type="button" onClick={() => load('')}>
                    전체 공모전 보기
                  </button>
                }
              />
            ) : (
              <ul className={styles.grid} aria-label="공모전 결과">
                {result.items.map((contest) => {
                  const url = originalUrl(contest);
                  return (
                    <li className={styles.card} key={contest.id}>
                      <div className={styles.cardTop}>
                        <span className="tag">{contest.is_demo ? '실습용 가상 공고' : contest.source}</span>
                        {contest.matched_keywords.length > 0 && (
                          <span className="tiny muted">키워드 {contest.matched_keywords.length}개 일치</span>
                        )}
                      </div>
                      <h3 className={styles.cardTitle}>{contest.title}</h3>
                      <p className="tiny muted">출처: {contest.source}</p>
                      {contest.recommendation_reason && (
                        <p className={styles.reason}>{contest.recommendation_reason}</p>
                      )}
                      <div className={styles.cardAction}>
                        {url ? (
                          <a className="btn btn-sm" href={url} target="_blank" rel="noopener noreferrer">
                            {contest.source}에서 공고 확인하기 ↗
                          </a>
                        ) : (
                          <button className="btn btn-sm" type="button" disabled>
                            {contest.is_demo ? '테스트 공고 · 원문 없음' : '원문 링크 없음'}
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        )}
      </section>

      <p className="hint">
        제목 키워드를 비교하는 기초 추천입니다. 접수 여부, 마감일, 응모 자격은 판단하지 않습니다.
      </p>
    </>
  );
}
