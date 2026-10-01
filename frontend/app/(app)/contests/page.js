'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import EmptyState from '@/components/EmptyState';
import ContestInterestMemory from '@/components/ContestInterestMemory';
import ContestFeedback from '@/components/ContestFeedback';
import { api, getToken } from '@/lib/api';
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
  const [filters, setFilters] = useState({ query: '', field: '', eligibility: '', deadlineBefore: '', sort: 'deadline' });

  const { memory, ready } = useContestInterestMemory();
  const savedKeywords = memory?.keywords.join(', ') || '';
  const inputValue = input ?? savedKeywords;
  const activeKeywords = request?.mode === 'recommend' ? request.keywords : savedKeywords;

  useEffect(() => {
    if (!getToken()) return;
    let alive = true;
    api.memories.list().then((rows) => {
      const interests = rows.find((row) => row.memory_type === 'interest_tags');
      const tags = interests?.value?.tags;
      if (alive && Array.isArray(tags) && tags.length) load(tags.join(', '));
    }).catch(() => {});
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    const keywords = splitKeywords(activeKeywords);
    const search = request?.mode === 'filters'
      ? api.contests.search({ ...request.filters, limit: 20 }, { signal: controller.signal })
          .then((data) => ({ items: data.items.map((item) => ({ ...item, matched: [] })), total: data.total, keywords: [] }))
      : searchByKeywords(keywords, { signal: controller.signal });
    search
      .then((data) => {
        if (!controller.signal.aborted) {
          setResult({ ...data, keywords: request?.mode === 'filters' ? [] : keywords });
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
    setRequest({ mode: 'recommend', keywords });
  }

  function searchWithFilters(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);
    setRequest({ mode: 'filters', filters: { ...filters } });
  }

  function retry() {
    setLoading(true);
    setError('');
    setResult(null);
    setRequest(request ? { ...request } : { mode: 'recommend', keywords: '' });
  }

  const recommended = request?.mode !== 'filters' && Boolean(result?.keywords.length);

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
          위비티 공고의 제목과 링크를 보여 줍니다. 출처를 확인하고 자세한 내용은 공고 원문에서 확인해 주세요.
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
              <button className="btn btn-orange" type="submit" disabled={loading}>
                {loading ? '불러오는 중…' : '추천받기'}
              </button>
            </div>
            <p id="contest-interest-help" className="hint">
              여러 키워드는 쉼표로 구분하세요. 공고 제목에 일치하는 키워드로 추천합니다.
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

      <section className={styles.searchPanel} aria-labelledby="contest-filter-heading">
        <h2 id="contest-filter-heading" className={styles.sectionTitle}>조건으로 공모전 찾기</h2>
        <form className={styles.filterGrid} onSubmit={searchWithFilters}>
          <label className="field">검색어
            <input className="input" value={filters.query} maxLength={100} placeholder="제목 또는 주최"
              onChange={(event) => setFilters((old) => ({ ...old, query: event.target.value }))} />
          </label>
          <label className="field">분야 (정확한 명칭)
            <input className="input" value={filters.field} maxLength={50} placeholder="예: 과학/공학"
              onChange={(event) => setFilters((old) => ({ ...old, field: event.target.value }))} />
          </label>
          <label className="field">응모 대상
            <input className="input" value={filters.eligibility} maxLength={100} placeholder="예: 대학생"
              onChange={(event) => setFilters((old) => ({ ...old, eligibility: event.target.value }))} />
          </label>
          <label className="field">이 날짜까지 마감
            <input className="input" type="date" value={filters.deadlineBefore}
              onChange={(event) => setFilters((old) => ({ ...old, deadlineBefore: event.target.value }))} />
          </label>
          <label className="field">정렬
            <select className="input" value={filters.sort}
              onChange={(event) => setFilters((old) => ({ ...old, sort: event.target.value }))}>
              <option value="deadline">마감 임박순</option>
              <option value="latest">최신순</option>
            </select>
          </label>
          <button className="btn btn-sm" type="submit" disabled={loading}>조건 검색</button>
        </form>
        <p className="hint">위비티 제목·링크 전용 공고는 분야·마감일·응모 대상 정보가 없어 해당 조건을 적용하면 결과에서 제외됩니다.</p>
      </section>

      <ContestInterestMemory draftKeywords={inputValue} onApply={load} disabled={loading} />

      <section className={styles.results} aria-labelledby="contest-results-heading" aria-busy={loading}>
        <div className="sec-head">
          <h2 id="contest-results-heading" className={styles.sectionTitle}>
            {request?.mode === 'filters' ? '조건 검색 결과' : recommended ? '관심 키워드 추천' : '공모전 목록'}
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
                <button className="btn btn-sm" type="button" onClick={retry}>
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
                적용한 키워드: {result.keywords.join(', ')} · 제목 기준
              </p>
            )}
            {result.items.length === 0 ? (
              <EmptyState
                title="일치하는 공모전이 없습니다"
                description="검색 조건을 줄이거나 전체 공모전을 확인해 보세요."
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
                  const limited = !contest.deadline; // 마감일이 비어 있는 옛 링크 전용 행
                  const left = contest.deadline ? daysLeft(contest.deadline) : null;
                  return (
                    <li className={styles.card} key={contest.id}>
                      <div className={styles.cardTop}>
                        {recommended && <span className="pill">{contest.aiGenerated ? 'AI 추천' : '키워드 추천'}</span>}
                        {!limited && left !== null && <span className={left <= 7 ? 'tag tag-late' : 'tag'}>
                          {contest.status === 'upcoming' ? '접수 예정' : dday(left)}
                        </span>}
                        {contest.matched.length > 0 && (
                          <span className="tiny muted">{contest.aiGenerated ? 'AI가 검토한 관심 태그' : '근거 태그'}: {contest.matched.join(', ')}</span>
                        )}
                      </div>
                      <h3 className={styles.cardTitle}>
                        <Link href={`/contests/${contest.id}`}>{contest.title}</Link>
                      </h3>
                      <p className="tiny muted">출처: {source}</p>
                      {!limited && <p className="tiny muted">
                        {contest.host} · 마감 {contest.deadline}
                        {contest.eligibility_text ? ` · ${contest.eligibility_text}` : ''}
                      </p>}
                      {!limited && contest.fields.length > 0 && (
                        <p className="tiny dim">{contest.fields.slice(0, 3).join(' · ')}</p>
                      )}
                      <div className={styles.cardAction} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {!limited && <Link className="btn btn-sm" href={`/contests/${contest.id}`}>준비 기간 계산</Link>}
                        {url && (
                          <a className="btn btn-sm btn-quiet" href={url} target="_blank" rel="noopener noreferrer">
                            {limited ? '위비티에서 공고 확인하기 ↗' : `${source} 원문 ↗`}
                          </a>
                        )}
                      </div>
                      {recommended && contest.reason && <p className="tiny muted">
                        {contest.aiGenerated && <strong>AI 추천 · </strong>}{contest.reason}
                      </p>}
                      {recommended && <ContestFeedback contestId={contest.id} />}
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        )}
      </section>

      <p className="hint">
        제목 키워드 또는 Claude가 제목과 관심 키워드를 비교해 찾은 추천입니다. AI 추천은 부정확할 수 있으며 응모 자격 충족 여부는 판단하지 않습니다.
      </p>
    </>
  );
}
