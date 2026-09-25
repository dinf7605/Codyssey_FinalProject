'use client';

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { api, getToken } from '@/lib/api';
import { loadExploration } from '@/lib/goalSession';
import { planInput } from '@/lib/planInput';
import { notifyPlanChanged } from '@/lib/usePlan';
import { AiBadge, AiNotice } from './AiNotice';

// FR-PLAN-02 학습 분해(AI Agent) → FR-PLAN-03 배치 → 규칙 검증
//
// 에이전트는 최대 60초가 걸린다 (NFR-PERF-01).
// 그동안 멈춘 화면을 보여주지 않으려고, 서버가 보내 주는 "실제로 한 일"을 그대로 적는다.
// 타이머로 단계를 지어내지 않는다 — 에이전트가 검색을 안 했으면 검색했다고 쓰지 않는다.

const BUDGET_SECONDS = 60;

const TOOL_LABEL = {
  search_curriculum: '출제 범위 검색',
  get_goal_catalog: '목표 정보 확인',
  get_available_slots: '빈 시간 확인',
  estimate_effort: '공부량 추정',
  search_contests: '관련 공모전 확인',
  save_plan: '저장 요청',
};

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];
const PREVIEW_UNITS = 6;

function statusText(event) {
  if (!event) return '연결하는 중';
  if (event.type === 'thinking') return event.step === 1 ? '목표를 읽는 중' : '찾은 자료로 계획을 정리하는 중';
  if (event.type === 'tool') return `${TOOL_LABEL[event.name] || '자료 확인'} 중`;
  if (event.type === 'retry') return '형식을 다시 맞추는 중';
  if (event.type === 'fallback') return '기본 계획으로 전환하는 중';
  return '마무리하는 중';
}

// 온보딩 값은 브라우저 저장소에 있다. 서버에서 그린 화면과 어긋나지 않게
// 서버에서는 'server', 브라우저에서는 저장된 값(문자열)을 스냅숏으로 쓴다.
function subscribeStorage(onChange) {
  window.addEventListener('storage', onChange);
  return () => window.removeEventListener('storage', onChange);
}
const readSaved = () => JSON.stringify(loadExploration());
const readSavedOnServer = () => 'server';

function blockWhen(iso) {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${d.getMonth() + 1}/${d.getDate()} (${WEEKDAY[d.getDay()]}) ${hh}:${mm}`;
}

export default function PlanBuilder() {
  const [phase, setPhase] = useState('idle'); // idle | running | done | error
  const saved = useSyncExternalStore(subscribeStorage, readSaved, readSavedOnServer);
  const input = useMemo(() => (saved === 'server' ? null : planInput(JSON.parse(saved))), [saved]);
  const [last, setLast] = useState(null);
  const [tools, setTools] = useState([]); // [{name, count}] 처음 부른 순서대로
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState(null);
  const [plan, setPlan] = useState(null);
  const [violations, setViolations] = useState(null);
  const [error, setError] = useState('');
  const [showAll, setShowAll] = useState(false);
  // 확정 — idle | saving | saved | login | error
  const [saveState, setSaveState] = useState({ state: 'idle', message: '' });
  // FR-PLAN-02 — 공부량이 가용시간의 1.5배를 넘으면 범위 축소안. used 는 지금 배치에 쓴 단위·기한
  const [scope, setScope] = useState(null);
  const [used, setUsed] = useState(null); // { mode: 'as-is' | 'trim' | 'extend', units, deadline }
  const [placing, setPlacing] = useState(false);
  const abortRef = useRef(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (phase !== 'running') return undefined;
    const started = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 500);
    return () => clearInterval(id);
  }, [phase]);

  function onEvent(event) {
    setLast(event);
    if (event.type !== 'tool') return;
    setTools((prev) => {
      const found = prev.find((t) => t.name === event.name);
      if (found) return prev.map((t) => (t === found ? { ...t, count: t.count + 1 } : t));
      return [...prev, { name: event.name, count: 1 }];
    });
  }

  async function run() {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const current = input;
    setPhase('running');
    setLast(null);
    setTools([]);
    setElapsed(0);
    setResult(null);
    setPlan(null);
    setViolations(null);
    setError('');
    setSaveState({ state: 'idle', message: '' });
    setShowAll(false);
    setScope(null);
    setUsed(null);

    try {
      const decomposed = await api.plan.decomposeStream(
        { ...current, signal: controller.signal },
        onEvent,
      );
      setResult(decomposed);

      // 공부량 점검은 참고용이다 — 실패해도 계획 만들기는 계속한다
      api.plan
        .scope({
          units: decomposed.units,
          availability: current.availability,
          startDay: current.startDay,
          deadline: current.deadline,
        })
        .then(setScope, () => setScope(null));

      await place('as-is', decomposed.units, current.deadline, current);
      setPhase('done');
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err.message || '계획을 만들지 못했습니다.');
      setPhase('error');
    }
  }

  // 배치와 검증은 LLM을 쓰지 않는다 — 규칙대로 놓고, 규칙을 어겼는지 다시 잰다
  async function place(mode, units, deadline, current = input) {
    const placed = await api.plan.schedule({
      units,
      availability: current.availability,
      startDay: current.startDay,
      deadline,
    });
    const check = await api.plan.validate({ blocks: placed.blocks, units, deadline });
    setPlan(placed);
    setViolations(check.violations);
    setUsed({ mode, units, deadline });
    setSaveState({ state: 'idle', message: '' });
  }

  async function adjust(mode) {
    setPlacing(true);
    try {
      if (mode === 'trim') {
        const keep = new Set(scope.keep_unit_ids);
        await place('trim', result.units.filter((u) => keep.has(u.id)), input.deadline);
      } else if (mode === 'extend') {
        await place('extend', result.units, scope.suggested_deadline);
      } else {
        await place('as-is', result.units, input.deadline);
      }
    } catch (err) {
      setError(err.message || '다시 배치하지 못했습니다.');
      setPhase('error');
    } finally {
      setPlacing(false);
    }
  }

  if (!input) return null;

  const weeklyHours = input.availability.slots.reduce((sum, s) => {
    const [sh, sm] = s.start.split(':').map(Number);
    const [eh, em] = s.end.split(':').map(Number);
    return sum + (eh * 60 + em - sh * 60 - sm) / 60;
  }, 0);
  // 에이전트의 save_plan 은 "사용자 확인 필요" 로 멈춘다 — 여기서 사람이 누른다 (AI기능명세 2)
  async function confirmPlan() {
    if (!getToken()) {
      setSaveState({ state: 'login', message: '' });
      return;
    }
    setSaveState({ state: 'saving', message: '' });
    try {
      await api.plan.save({
        goalTitle: input.goalTitle,
        goalId: input.goalId,
        source: result.source,
        units: used.units,
        blocks: plan.blocks,
        deadline: used.deadline,
        availability: input.availability,
      });
      setSaveState({ state: 'saved', message: '' });
      notifyPlanChanged(); // 같은 화면의 일정 달력이 새 계획을 다시 읽는다
    } catch (err) {
      if (err.status === 401 || err.status === 403) {
        setSaveState({ state: 'login', message: '' });
      } else {
        setSaveState({ state: 'error', message: err.message || '저장하지 못했습니다.' });
      }
    }
  }

  const isAi = result && result.source !== 'template';
  const units = result ? (showAll ? result.units : result.units.slice(0, PREVIEW_UNITS)) : [];
  const estimatedCount = result ? result.units.filter((u) => u.estimated).length : 0;

  return (
    <div className="stack plan-builder" style={{ gap: 'var(--gap-4)' }}>
      <div className="row" style={{ borderBottom: 0, paddingBottom: 0 }}>
        <div className="row-main">
          <b>{input.goalTitle}</b>
          <span>
            {input.weeks}주 · 주 {Math.round(weeklyHours)}시간 ·{' '}
            {input.fromOnboarding ? '온보딩에서 고른 시간' : '기본값: 평일 저녁'}
          </span>
        </div>
        {phase === 'done' && (
          <button type="button" className="btn btn-quiet btn-sm" onClick={run}>
            다시 만들기
          </button>
        )}
      </div>

      {phase === 'idle' && (
        <>
          <button type="button" className="btn btn-primary" onClick={run}>
            AI로 학습 계획 만들기
          </button>
          <p className="hint">
            출제 범위를 찾아 공부 단위로 나눈 뒤 빈 시간에 배치합니다. 최대 1분 걸리고,
            넘기면 표준 커리큘럼으로 시작합니다.
          </p>
        </>
      )}

      {phase === 'running' && (
        <div className="progress" role="status" aria-live="polite">
          <div className="progress-head">
            <b>{statusText(last)}</b>
            <span className="tag">
              {elapsed}초 / 최대 {BUDGET_SECONDS}초
            </span>
          </div>
          <div className="bar">
            <div
              className="bar-fill"
              style={{ width: `${Math.min(100, (elapsed / BUDGET_SECONDS) * 100)}%` }}
            />
          </div>
          {tools.length > 0 && (
            <ul className="progress-log">
              {tools.map((t) => (
                <li key={t.name}>
                  <span>{TOOL_LABEL[t.name] || t.name}</span>
                  <span className="tag">{t.count > 1 ? `${t.count}회` : '완료'}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {phase === 'error' && (
        <div className="stack" style={{ gap: 'var(--gap-2)' }}>
          <p className="hint hint-error">{error}</p>
          <button type="button" className="btn" onClick={run}>
            다시 시도
          </button>
        </div>
      )}

      {phase === 'done' && result && (
        <>
          <div className="stack" style={{ gap: 'var(--gap-2)' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              {isAi ? <AiBadge /> : <span className="pill">기본 계획</span>}
              <span className="tag">
                학습 단위 {result.units.length}개
                {estimatedCount > 0 && ` · 추정 ${estimatedCount}개`}
                {result.tool_calls > 0 && ` · 자료 확인 ${result.tool_calls}회`}
              </span>
            </div>
            {result.message && <p className="hint">{result.message}</p>}
          </div>

          <ol className="rows">
            {units.map((u) => (
              <li className="row" key={u.id}>
                <div className="row-main">
                  <b>{u.title}</b>
                  <span>
                    {u.estimated_minutes}분
                    {u.prerequisites.length > 0 && ' · 앞 단위를 끝낸 뒤'}
                  </span>
                </div>
                {u.estimated && <span className="pill">추정</span>}
              </li>
            ))}
          </ol>
          {result.units.length > PREVIEW_UNITS && (
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => setShowAll((v) => !v)}>
              {showAll ? '접기' : `나머지 ${result.units.length - PREVIEW_UNITS}개 보기`}
            </button>
          )}

          {isAi && (
            <AiNotice>
              AI가 나눈 학습 단위라 실제 출제 범위와 다를 수 있습니다. ‘추정’은 검색한 자료
              밖에서 AI가 짐작한 단위입니다.
            </AiNotice>
          )}

          {scope?.over && (
            <ScopeNotice scope={scope} units={result.units} used={used} busy={placing} onPick={adjust} />
          )}

          {plan && (
            <div className="stack" style={{ gap: 'var(--gap-2)' }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <b style={{ fontSize: 14 }}>빈 시간에 {plan.blocks.length}개 배치</b>
                {violations && (
                  <span className={violations.length ? 'pill pill-late' : 'pill pill-ok'}>
                    {violations.length ? `규칙 위반 ${violations.length}건` : '규칙 위반 0건'}
                  </span>
                )}
              </div>
              <ol className="rows">
                {plan.blocks.slice(0, 3).map((b) => (
                  <li className="row" key={b.id}>
                    <div className="row-main">
                      <b>{b.title}</b>
                      <span>{blockWhen(b.start)}</span>
                    </div>
                    <span className="tag">{b.minutes}분</span>
                  </li>
                ))}
              </ol>
              {/* 못 넣은 단위가 있으면 서버가 조정 안내를 notes 에 담아 보낸다 */}
              {plan.notes.map((note) => (
                <p className={plan.unplaced.length ? 'hint hint-error' : 'hint'} key={note}>
                  {note}
                </p>
              ))}
              <p className="hint">
                배치는 AI가 아니라 규칙으로 합니다 — 선행 순서, 하루 3블록, 연속 2시간, 쉬는 날을
                지킵니다. 캘린더 저장은 연동 후 열립니다.
              </p>

              {/* 규칙 위반이 0건이고 놓인 블록이 있을 때만 확정할 수 있다 — 서버도 한 번 더 검사한다 */}
              {violations && violations.length === 0 && plan.blocks.length > 0 && (
                <div className="stack" style={{ gap: 'var(--gap-2)' }}>
                  {saveState.state === 'saved' ? (
                    <p className="hint" style={{ color: 'var(--ok)' }}>
                      계획을 저장했습니다. 위 &apos;내 학습 일정&apos;에서 확인할 수 있어요. 다시 만들면 이전 계획은 보관됩니다.
                    </p>
                  ) : saveState.state === 'login' ? (
                    <p className="hint">
                      로그인하면 이 계획을 저장할 수 있어요. <a href="/login?next=/schedule">로그인하기</a>
                    </p>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={confirmPlan}
                      disabled={saveState.state === 'saving'}
                    >
                      {saveState.state === 'saving' ? '저장하는 중' : '이 계획으로 확정'}
                    </button>
                  )}
                  {saveState.state === 'error' && <p className="hint hint-error">{saveState.message}</p>}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

const hours = (minutes) => Math.round((minutes / 60) * 10) / 10;

// FR-PLAN-02 — "총 소요시간이 가용시간의 1.5배를 넘으면 범위 축소안을 함께 제시"
// 고르지 않으면 그대로 배치하고, 못 넣은 단위는 '미배치'로 남는다.
function ScopeNotice({ scope, units, used, busy, onPick }) {
  const dropped = units.filter((u) => scope.drop_unit_ids.includes(u.id));
  const mode = used?.mode || 'as-is';
  const deadlineText = scope.suggested_deadline
    ? `${Number(scope.suggested_deadline.slice(5, 7))}/${Number(scope.suggested_deadline.slice(8, 10))}`
    : null;
  return (
    <div className="progress" role="note" aria-label="공부량 점검">
      <b>
        {scope.ratio
          ? `공부량이 기한까지 쓸 수 있는 시간의 ${scope.ratio}배예요`
          : '기한까지 공부할 수 있는 시간이 없어요'}
      </b>
      <p className="muted tiny">
        필요 {hours(scope.total_minutes)}시간 · 기한까지 빈 시간 {hours(scope.available_minutes)}시간. 둘 중 하나를
        고르거나 그대로 두면 못 넣은 단위는 미배치로 남습니다.
      </p>
      <div style={{ display: 'flex', gap: 'var(--gap-2)', flexWrap: 'wrap' }}>
        {dropped.length > 0 && (
          <button type="button" className="chip" aria-pressed={mode === 'trim'} disabled={busy} onClick={() => onPick('trim')}>
            범위 줄이기 · 뒤쪽 {dropped.length}개 빼기
          </button>
        )}
        {deadlineText && (
          <button type="button" className="chip" aria-pressed={mode === 'extend'} disabled={busy} onClick={() => onPick('extend')}>
            기한을 {deadlineText}로 늘리기
          </button>
        )}
        {mode !== 'as-is' && (
          <button type="button" className="chip" disabled={busy} onClick={() => onPick('as-is')}>
            원래대로
          </button>
        )}
      </div>
      {mode === 'trim' && (
        <p className="hint">뺀 단위: {dropped.map((u) => u.title).join(', ')}</p>
      )}
    </div>
  );
}
