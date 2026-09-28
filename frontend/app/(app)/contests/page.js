'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import EmptyState from '@/components/EmptyState';
import ContestInterestMemory from '@/components/ContestInterestMemory';
import { useContestInterestMemory } from '@/lib/contest-interest-memory';
import { SOURCE_LABEL, daysLeft, safeUrl, searchByKeywords } from '@/lib/contests';
import { dday } from '@/lib/ui';
import styles from './contests.module.css';

// FR-CONT-03 공모전 검색 — 위비티에서 모은 실제 공고 (담당 D, 수집기 services/wevity_collector.py)
// 관심 키워드가 제목·주최에 들어간 공고를 찾고, 많이 맞은 공고 · 마감 임박순으로 보여 준다.

const SUGGESTIONS = ['AI', '아이디어', '영상', '창업', '해커톤', '디자인']; // 수집한 공고에 실제로 많이 나오는 말 (09-28 기준)
const splitKeywords = (text) => text.split(',').map((k) => k.trim()).filter(Boolean);

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
    const keywords = splitKeywords(activeKeywords);
    searchByKeywords(keywords, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) {
          setResult({ ...data, keywords });
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

      <aside className={styles.notice} aria-label="공고 출처 안내">
        <strong>공고 출처: 위비티</strong>
        <p>
          위비티에 올라온 공모전 중 접수 중인 공고의 제목·주최·기간만 모아 보여 줍니다. 매일 새벽에 새로 모아요.
          지원 자격과 자세한 내용은 반드시 공고 원문에서 확인해 주세요.
        </p>
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
              여러 키워드는 쉼표로 구분하세요. 제목·주최에 키워드가 많이 들어간 공고부터, 같으면 마감 임박순으로 보여 줍니다.
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
            {loading ? '불러오는 중' : error ? '연결 확인 필요' : result && result.total > result.items.length ? `${result.total}개 중 ${result.items.length}개` : `${result?.total ?? 0}개`}
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
                적용한 키워드: {result.keywords.join(', ')} · 제목·주최 기준
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
                  const url = safeUrl(contest.source_url);
                  const source = SOURCE_LABEL[contest.source] || contest.source;
                  const left = daysLeft(contest.deadline);
                  return (
                    <li className={styles.card} key={contest.id}>
                      <div className={styles.cardTop}>
                        <span className={left <= 7 ? 'tag tag-late' : 'tag'}>
                          {contest.status === 'upcoming' ? '접수 예정' : dday(left)}
                        </span>
                        {contest.matched.length > 0 && (
                          <span className="tiny muted">키워드 {contest.matched.length}개 일치</span>
                        )}
                      </div>
                      <h3 className={styles.cardTitle}>
                        <Link href={`/contests/${contest.id}`}>{contest.title}</Link>
                      </h3>
                      <p className="tiny muted">
                        {contest.host} · 마감 {contest.deadline}
                        {contest.eligibility_text ? ` · ${contest.eligibility_text}` : ''}
                      </p>
                      {contest.fields.length > 0 && (
                        <p className="tiny dim">{contest.fields.slice(0, 3).join(' · ')}</p>
                      )}
                      <div className={styles.cardAction} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <Link className="btn btn-sm" href={`/contests/${contest.id}`}>준비 기간 계산</Link>
                        {url && (
                          <a className="btn btn-sm btn-quiet" href={url} target="_blank" rel="noopener noreferrer">
                            {source} 원문 ↗
                          </a>
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
        제목·주최의 키워드를 비교하는 기초 검색입니다. 응모 자격을 충족하는지는 판단하지 않습니다.
      </p>
    </>
  );
}
