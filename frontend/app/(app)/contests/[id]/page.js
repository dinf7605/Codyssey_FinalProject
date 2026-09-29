'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import EmptyState from '@/components/EmptyState';
import { api, getToken } from '@/lib/api';
import { saveContestPlanning } from '@/lib/contest-planning';
import { SOURCE_LABEL, daysLeft, safeUrl } from '@/lib/contests';
import { dday } from '@/lib/ui';

// FR-CONT-10 준비 기간 산정 — 비회원도 로그인 없이 계산할 수 있다.
// FR-CONT-11 계산 결과를 일정으로 만들려면 가입으로 유도한다.
// 계산은 서버의 결정론적 나눗셈이다 (표준 준비시간 ÷ 주당 투입 시간, LLM 미사용 · 기획서 4-2절).
// 공고 본문은 저장하지 않는다 — 자격·세부 내용은 원문 링크로 보낸다.

const VERDICT = {
  possible: { label: '가능', cls: 'pill pill-ok' },
  tight: { label: '빠듯함', cls: 'pill' },
  impossible: { label: '이번 회차는 어렵습니다', cls: 'pill pill-late' },
};
const HOURS_SOURCE = {
  exact: '이 분야의 표준 준비시간',
  group_median: '비슷한 분야의 중앙값',
  global_median: '전체 분야의 중앙값',
};

export default function ContestDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [state, setState] = useState({ status: 'loading', contest: null, error: '' });
  const [hours, setHours] = useState(8);
  const [manualDeadline, setManualDeadline] = useState('');
  const [manualField, setManualField] = useState('');
  const [estimate, setEstimate] = useState(null);
  const [estimateError, setEstimateError] = useState('');

  useEffect(() => {
    let alive = true;
    api.contests.get(id).then(
      (contest) => alive && setState({ status: 'ready', contest, error: '' }),
      (err) => alive && setState({ status: err.status === 404 ? 'missing' : 'error', contest: null, error: err.message }),
    );
    return () => { alive = false; };
  }, [id]);

  // 슬라이더를 움직이는 동안 매번 부르지 않게 잠깐 기다렸다 계산한다
  useEffect(() => {
    if (state.status !== 'ready') return;
    // 수집한 마감일이 없는 옛 링크 전용 행만 사용자가 원문에서 확인한 마감일을 넣는다
    const manual = !state.contest?.deadline;
    if (manual && !manualDeadline) return;
    let alive = true;
    const timer = setTimeout(() => {
      api.contests.estimate(id, hours, manual ? { deadline: manualDeadline, field: manualField } : {}).then(
        (res) => { if (alive) { setEstimate(res); setEstimateError(''); } },
        (err) => alive && setEstimateError(err.message || '준비 기간을 계산하지 못했습니다.'),
      );
    }, 250);
    return () => { alive = false; clearTimeout(timer); };
  }, [id, hours, manualDeadline, manualField, state.status, state.contest?.deadline]);

  if (state.status === 'loading') return <p className="hint">공고를 불러오는 중…</p>;
  if (state.status !== 'ready') {
    return (
      <EmptyState
        title={state.status === 'missing' ? '공고를 찾을 수 없습니다' : '공고를 불러오지 못했습니다'}
        description={state.status === 'missing' ? '마감되어 내려갔거나 주소가 잘못되었어요.' : state.error}
        action={<Link className="btn btn-sm" href="/contests">공모전 목록으로</Link>}
      />
    );
  }

  const c = state.contest;
  function continueToPlan() {
    if (!estimate) return;
    try {
      saveContestPlanning({
        contestId: c.id, title: c.title,
        deadline: c.deadline || manualDeadline,
        field: c.fields[0] || manualField,
        weeklyHours: hours, weeksNeeded: estimate.weeks_needed,
      });
      const destination = '/schedule#plan-builder';
      router.push(getToken() ? destination : `/signup?next=${encodeURIComponent(destination)}`);
    } catch (error) {
      setEstimateError(error.message || '계산값을 이 탭에 저장하지 못했습니다.');
    }
  }
  if (!c.deadline) {
    const url = safeUrl(c.source_url);
    return (
      <>
        <p className="hint"><Link href="/contests">← 공모전 목록</Link></p>
        <h1 style={{ fontSize: 21, overflowWrap: 'anywhere' }}>{c.title}</h1>
        <p className="muted">출처: 위비티</p>
        <p className="hint">지원 자격, 접수 기간, 제출 방법은 위비티의 공고 원문에서 확인해 주세요.</p>
        {url && <a className="btn btn-primary" href={url} target="_blank" rel="noopener noreferrer">위비티에서 공고 확인하기 ↗</a>}
        <section className="panel" style={{ padding: 'var(--gap-4)', marginTop: 'var(--gap-4)' }}>
          <h2 style={{ fontSize: 15 }}>준비 기간 계산</h2>
          <p className="hint">원문에서 마감일을 확인해 직접 입력해 주세요. 입력한 날짜·분야·시간은 서버에 저장하지 않습니다.</p>
          <div className="field" style={{ marginTop: 'var(--gap-3)' }}>
            <label htmlFor="wevity-deadline">원문에서 확인한 마감일</label>
            <input id="wevity-deadline" type="date" className="input" value={manualDeadline}
              onChange={(event) => { setManualDeadline(event.target.value); setEstimate(null); }} />
          </div>
          <div className="field" style={{ marginTop: 'var(--gap-3)' }}>
            <label htmlFor="wevity-field">분야 (선택)</label>
            <input id="wevity-field" className="input" value={manualField} maxLength={50}
              placeholder="예: 과학/공학" onChange={(event) => { setManualField(event.target.value); setEstimate(null); }} />
          </div>
          <div className="field" style={{ marginTop: 'var(--gap-3)' }}>
            <label htmlFor="wevity-hours">주당 투입 가능 시간: {hours}시간</label>
            <input id="wevity-hours" type="range" min={1} max={30} value={hours}
              onChange={(event) => { setHours(Number(event.target.value)); setEstimate(null); }} />
          </div>
          {estimateError && <p className="hint hint-error" role="alert">{estimateError}</p>}
          {estimate && <p className="hint" role="status">
            최소 {estimate.weeks_needed}주 · {VERDICT[estimate.verdict].label}. {estimate.message}
            {' '}기준 {estimate.standard_hours}시간 ({HOURS_SOURCE[estimate.hours_source]}, 추정치).
          </p>}
          <button type="button" className="btn btn-primary" disabled={!estimate || estimate.verdict === 'impossible'} onClick={continueToPlan}>
            이 준비 기간으로 일정 만들기
          </button>
        </section>
      </>
    );
  }
  const left = daysLeft(c.deadline);
  const source = SOURCE_LABEL[c.source] || c.source;
  const sourceUrl = safeUrl(c.source_url);
  const officialUrl = safeUrl(c.official_url);
  const verdict = estimate && VERDICT[estimate.verdict];

  return (
    <>
      <header className="stack" style={{ gap: 'var(--gap-2)' }}>
        <div style={{ display: 'flex', gap: 'var(--gap-2)', flexWrap: 'wrap' }}>
          <span className="pill mono">{c.status === 'upcoming' ? '접수 예정' : dday(left)}</span>
          {c.fields.slice(0, 3).map((f) => <span className="pill" key={f}>{f}</span>)}
        </div>
        <h1 style={{ fontSize: 19, lineHeight: 1.4, overflowWrap: 'anywhere' }}>{c.title}</h1>
        <p className="muted tiny">
          {c.host} · 접수 {c.start_date ? `${c.start_date} ~ ` : ''}{c.deadline}
        </p>
        {c.eligibility_text && <p className="muted tiny">응모 대상: {c.eligibility_text}</p>}
      </header>

      <section className="panel" style={{ padding: 'var(--gap-4)' }}>
        <h2 style={{ fontSize: 15 }}>공고 원문</h2>
        <p className="muted tiny" style={{ marginTop: 4 }}>
          지원 자격 충족 여부는 단정할 수 없습니다. 자세한 내용과 제출 방법은 반드시 원문에서 확인해 주세요.
        </p>
        <div style={{ display: 'flex', gap: 'var(--gap-2)', flexWrap: 'wrap', marginTop: 'var(--gap-3)' }}>
          {sourceUrl && (
            <a className="btn btn-sm" href={sourceUrl} target="_blank" rel="noopener noreferrer">{source}에서 보기 ↗</a>
          )}
          {officialUrl && (
            <a className="btn btn-sm btn-quiet" href={officialUrl} target="_blank" rel="noopener noreferrer">공식 홈페이지 ↗</a>
          )}
        </div>
      </section>

      <section className="panel" style={{ padding: 'var(--gap-4)' }}>
        <h2 style={{ fontSize: 15 }}>얼마나 준비해야 할까요</h2>
        <p className="muted tiny" style={{ marginTop: 4 }}>
          주당 투입 가능 시간을 넣으면 최소 준비 기간을 계산합니다
        </p>

        <div className="field" style={{ marginTop: 'var(--gap-4)' }}>
          <label htmlFor="hours">주당 투입 가능 시간: {hours}시간</label>
          <input
            id="hours"
            type="range"
            min={1}
            max={30}
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            style={{ width: '100%' }}
          />
        </div>

        {estimateError && <p className="hint hint-error" role="alert">{estimateError}</p>}
        {estimate && (
          <>
            <div
              style={{
                marginTop: 'var(--gap-3)',
                paddingTop: 'var(--gap-3)',
                borderTop: '1px solid var(--rule)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 'var(--gap-3)',
              }}
              aria-live="polite"
            >
              <div className="stack" style={{ gap: 2 }}>
                <span className="dim tiny">최소 필요 기간 · 마감까지 {estimate.weeks_left}주</span>
                <span className="mono" style={{ fontSize: 18, fontWeight: 600 }}>{estimate.weeks_needed}주</span>
              </div>
              <span className={verdict.cls}>{verdict.label}</span>
            </div>
            <p className="hint" style={{ marginTop: 'var(--gap-2)' }}>
              {estimate.message} {HOURS_SOURCE[estimate.hours_source]} {estimate.standard_hours}시간 기준이에요
              (팀 추정치 — 공식 통계가 아닙니다).
            </p>
          </>
        )}

        <button type="button" className="btn btn-primary" disabled={!estimate || estimate.verdict === 'impossible'}
          onClick={continueToPlan} style={{ marginTop: 'var(--gap-4)' }}>
          이 공모전 준비 일정 만들기
        </button>
        <p className="hint" style={{ marginTop: 6, textAlign: 'center' }}>
          일정 저장에는 가입이 필요합니다 · 계획 만들기에서 공모전 이름을 목표로 넣어 주세요
        </p>
      </section>
    </>
  );
}
