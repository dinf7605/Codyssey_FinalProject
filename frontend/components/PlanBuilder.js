'use client';

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { api } from '@/lib/api';
import { loadExploration } from '@/lib/goalSession';
import { planInput } from '@/lib/planInput';
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
    setShowAll(false);

    try {
      const decomposed = await api.plan.decomposeStream(
        { ...current, signal: controller.signal },
        onEvent,
      );
      setResult(decomposed);

      // 배치와 검증은 LLM을 쓰지 않는다 — 규칙대로 놓고, 규칙을 어겼는지 다시 잰다
      const placed = await api.plan.schedule({
        units: decomposed.units,
        availability: current.availability,
        startDay: current.today,
        deadline: current.deadline,
      });
      setPlan(placed);
      const check = await api.plan.validate({
        blocks: placed.blocks,
        units: decomposed.units,
        deadline: current.deadline,
      });
      setViolations(check.violations);
      setPhase('done');
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err.message || '계획을 만들지 못했습니다.');
      setPhase('error');
    }
  }

  if (!input) return null;

  const weeklyHours = input.availability.slots.reduce((sum, s) => {
    const [sh, sm] = s.start.split(':').map(Number);
    const [eh, em] = s.end.split(':').map(Number);
    return sum + (eh * 60 + em - sh * 60 - sm) / 60;
  }, 0);
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
                지킵니다. 확정·캘린더 저장은 연동 후 열립니다.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
