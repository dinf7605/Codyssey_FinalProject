'use client';

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { api, getToken } from '@/lib/api';
import { loadExploration } from '@/lib/goalSession';
import { clearContestPlanning, loadContestPlanning } from '@/lib/contest-planning';
import { planInput, slotsHours, weeksBetween } from '@/lib/planInput';
import { clearDraft, draftKey, loadDraft, saveDraft } from '@/lib/planDraft';
import { clearBusy, loadBusy, startCalendarConnect } from '@/lib/calendarBusy';
import { notifyPlanChanged, usePlan } from '@/lib/usePlan';
import { AiBadge, AiNotice } from './AiNotice';
import EmptyState from './EmptyState';

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

// 기한이 어디서 왔는지 — 사용자가 고른 날짜가 아니면 그렇다고 밝히고 바꿀 수 있게 한다
const DEADLINE_LABEL = {
  exam: '다음 시험일',
  manual: '직접 정한 기한',
  contest: '공모전 마감일',
  estimate: '권장 기간으로 잡은 기한',
  user: '직접 고친 기한',
};

// 확정한 계획의 관심분야를 계정 메모리(관심 분야)에 더한다 — 공모전 추천 · 마이페이지가 같은 값을 쓴다.
// 실패해도 계획 저장은 끝났으니 조용히 넘어간다.
async function rememberInterests(tags) {
  if (!tags?.length) return;
  try {
    const rows = await api.memories.list();
    const saved = rows.find((r) => r.memory_type === 'interest_tags')?.value?.tags || [];
    const merged = [...new Set([...saved, ...tags])].slice(0, 10);
    if (merged.length !== saved.length) await api.memories.saveInterests(merged);
  } catch {
    // 메모리 저장은 부가 기능이다
  }
}
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
const readSaved = () => JSON.stringify({ exploration: loadExploration(), contest: loadContestPlanning() });
const readSavedOnServer = () => 'server';

function blockWhen(iso) {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${d.getMonth() + 1}/${d.getDate()} (${WEEKDAY[d.getDay()]}) ${hh}:${mm}`;
}

export default function PlanBuilder() {
  // 확정 전에 만들어 둔 계획 — 있으면 그 상태로 이어서 보여준다 (lib/planDraft.js)
  // 서버 렌더에서는 null 이고, 브라우저 첫 렌더는 input 이 없어 어차피 아무것도 그리지 않는다
  const [draft] = useState(loadDraft);
  const [restoredKey, setRestoredKey] = useState(draft?.key ?? null);
  const [phase, setPhase] = useState(draft ? 'done' : 'idle'); // idle | running | done | error
  const saved = useSyncExternalStore(subscribeStorage, readSaved, readSavedOnServer);
  const baseInput = useMemo(() => {
    if (saved === 'server') return null;
    const state = JSON.parse(saved);
    return planInput(state.exploration, new Date(), state.contest);
  }, [saved]);
  // 사용자가 고친 기한 — 목표가 바뀌면 버린다. 보관본에 있으면 이어받는다
  const [deadlineEdit, setDeadlineEdit] = useState(draft?.deadlineEdit ?? null);
  const active = usePlan();
  const input =
    baseInput && deadlineEdit && deadlineEdit.goal === baseInput.goalTitle
      ? { ...baseInput, deadline: deadlineEdit.value, deadlineSource: 'user' }
      : baseInput;
  const [last, setLast] = useState(null);
  const [tools, setTools] = useState([]); // [{name, count}] 처음 부른 순서대로
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState(draft?.result ?? null);
  const [plan, setPlan] = useState(draft?.plan ?? null);
  const [violations, setViolations] = useState(draft?.violations ?? null);
  const [error, setError] = useState('');
  const [showAll, setShowAll] = useState(false);
  // 확정 — idle | saving | saved | login | error
  const [saveState, setSaveState] = useState({ state: 'idle', message: '' });
  // FR-PLAN-02 — 공부량이 가용시간의 1.5배를 넘으면 범위 축소안. used 는 지금 배치에 쓴 단위·기한
  const [scope, setScope] = useState(draft?.scope ?? null);
  const [used, setUsed] = useState(draft?.used ?? null); // { mode: 'as-is' | 'trim' | 'extend', units, deadline }
  const [placing, setPlacing] = useState(false);
  // FR-PLAN-01 구글 캘린더에서 가져온 바쁜 시간 (이 탭에 30분) — lib/calendarBusy.js
  const [calendar, setCalendar] = useState(loadBusy);
  const [calendarState, setCalendarState] = useState({ pending: false, error: '' });
  const abortRef = useRef(null);

  // 보관본이 지금 입력(목표·시작일·기한·가용시간)과 다르면 되살리지 않고 처음 화면을 보여준다
  const key = input ? draftKey(input) : null;
  const stale = restoredKey !== null && key !== null && restoredKey !== key;
  const view = stale ? 'idle' : phase;

  useEffect(() => () => abortRef.current?.abort(), []);

  // 만든 계획을 확정 전까지 보관한다 — 비회원이 로그인하러 다녀오거나, 회원이 다른 화면을 보고 와도
  // 1분 가까이 걸린 AI 결과를 다시 만들 필요가 없게 (10-01 실사용: 회원은 화면을 옮기면 사라졌다).
  // 범위 줄이기·기한 바꾸기로 다시 놓으면 그 결과로 덮어쓴다. 확정하면 지운다.
  useEffect(() => {
    if (view !== 'done' || !key || !result || !plan || saveState.state === 'saved') return;
    saveDraft(key, { result, plan, violations, scope, used, deadlineEdit });
  }, [view, key, result, plan, violations, scope, used, deadlineEdit, saveState.state]);

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
    clearDraft();
    setRestoredKey(null);
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
      goalTitle: current.goalTitle,
      busy: calendar?.busy || [], // FR-PLAN-01 가져온 구글 캘린더 일정 시간은 비켜 간다
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

  // 고른 목표가 없다 — 아무 목표로나 계획을 만들지 않고 목표 정하기로 보낸다
  if (!input.goalTitle) {
    return (
      <EmptyState
        title="먼저 목표를 정해 주세요"
        description="관심분야와 공부할 수 있는 시간을 알려 주시면 맞는 목표를 찾아 드려요. 공모전 화면에서 고른 공모전으로도 만들 수 있어요."
        action={
          <div style={{ display: 'flex', gap: 'var(--gap-2)', justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link className="btn btn-primary btn-sm" href="/onboarding">목표 정하기</Link>
            <Link className="btn btn-sm" href="/contests">공모전 둘러보기</Link>
          </div>
        }
      />
    );
  }

  const weeklyHours = slotsHours(input.availability.slots);
  const full =
    active.status === 'ready' &&
    active.maxPlans > 0 &&
    active.plans.length >= active.maxPlans &&
    !active.plans.some((p) => p.goal_title === input.goalTitle);
  const deadlineValid = input.deadline > input.startDay;
  // 확정한 뒤에는 고치지 않는다 — 저장된 계획은 일정 화면에서 다룬다
  const editable = view !== 'running' && saveState.state !== 'saved';

  function changeDeadline(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return;
    setDeadlineEdit({ goal: baseInput.goalTitle, value });
    // 학습 단위는 기한과 무관하다 — AI를 다시 부르지 않고 새 기한으로 배치만 다시 한다
    if (view !== 'done' || !result || value <= input.startDay) return;
    const next = { ...input, deadline: value, deadlineSource: 'user' };
    setRestoredKey(null);
    setScope(null);
    api.plan
      .scope({ units: result.units, availability: next.availability, startDay: next.startDay, deadline: value })
      .then(setScope, () => setScope(null));
    setPlacing(true);
    place('as-is', result.units, value, next)
      .catch((err) => {
        setError(err.message || '다시 배치하지 못했습니다.');
        setPhase('error');
      })
      .finally(() => setPlacing(false));
  }
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
      rememberInterests(input.tags);
      clearDraft(); // 저장했으니 보관본은 필요 없다
      setRestoredKey(null);
      if (input.fromContest) clearContestPlanning();
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
            {DEADLINE_LABEL[input.deadlineSource]} {input.deadline}
            {deadlineValid && ` (${weeksBetween(input.startDay, input.deadline)}주)`} · 주 {weeklyHours}시간 ·{' '}
            {input.fromContest ? '공모전 화면에서 정한 시간' : input.fromOnboarding ? '온보딩에서 고른 시간' : '기본값: 평일 저녁'}
          </span>
        </div>
        {view === 'done' && (
          <button type="button" className="btn btn-quiet btn-sm" onClick={run}>
            다시 만들기
          </button>
        )}
      </div>

      {editable && (
        <div className="field">
          <label htmlFor="plan-deadline">시험일·마감일</label>
          <input
            id="plan-deadline"
            className="input"
            type="date"
            min={input.startDay}
            value={input.deadline}
            disabled={placing}
            onChange={(e) => changeDeadline(e.target.value)}
          />
          <p className={deadlineValid ? 'hint' : 'hint hint-error'}>
            {!deadlineValid
              ? '기한은 첫 공부일보다 뒤여야 해요.'
              : input.deadlineSource === 'estimate'
                ? '시험일이나 마감일이 정해져 있다면 그 날짜로 바꿔 주세요. 지금은 권장 기간으로 잡은 날짜예요.'
                : '날짜가 다르면 바꿔 주세요. 이 날짜까지 끝나도록 배치합니다.'}{' '}
            <Link href="/onboarding">목표 바꾸기</Link>
          </p>
        </div>
      )}

      {editable && (
        <div className="stack" style={{ gap: 6 }}>
          {calendar ? (
            <p className="hint" style={{ margin: 0 }}>
              구글 캘린더 일정 {calendar.busy.length}개를 피해서 놓아요.{' '}
              <button type="button" className="btn-link" disabled={placing}
                onClick={() => { clearBusy(); setCalendar(null); }}>빼기</button>
            </p>
          ) : (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <button type="button" className="btn btn-sm" disabled={calendarState.pending || !deadlineValid}
                onClick={async () => {
                  setCalendarState({ pending: true, error: '' });
                  try {
                    await startCalendarConnect({ startDay: input.startDay, deadline: input.deadline });
                  } catch (err) {
                    setCalendarState({ pending: false, error: err.message || '구글 캘린더에 연결하지 못했어요.' });
                  }
                }}>
                {calendarState.pending ? '구글로 이동하는 중…' : '구글 캘린더에서 바쁜 시간 가져오기'}
              </button>
              <span className="micro dim">일정 제목은 읽지 않고, 한 번 읽은 뒤 권한을 바로 돌려드려요</span>
            </div>
          )}
          {calendarState.error && <p className="hint hint-error" role="alert" style={{ margin: 0 }}>{calendarState.error}</p>}
        </div>
      )}

      {/* 진행 중 목표가 이미 가득 찼으면 1분 걸려 만든 뒤 저장에서 막히지 않게 미리 알린다 (같은 목표를 다시 만드는 건 교체라 괜찮다) */}
      {full && (
        <p className="hint hint-error" role="alert">
          진행 중인 목표가 {active.maxPlans}개라 새 목표의 계획은 저장할 수 없어요.{' '}
          <Link href="/mypage#goal-settings">목표 관리</Link>에서 하나를 끝내면 만들 수 있어요.
        </p>
      )}

      {view === 'idle' && (
        <>
          <button type="button" className="btn btn-primary" onClick={run} disabled={!deadlineValid || full}>
            AI로 학습 계획 만들기
          </button>
          <p className="hint">
            출제 범위를 찾아 공부 단위로 나눈 뒤 빈 시간에 배치합니다. 최대 1분 걸리고,
            넘기면 표준 커리큘럼으로 시작합니다.
          </p>
        </>
      )}

      {view === 'running' && (
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

      {view === 'error' && (
        <div className="stack" style={{ gap: 'var(--gap-2)' }}>
          <p className="hint hint-error">{error}</p>
          <button type="button" className="btn" onClick={run} disabled={!deadlineValid}>
            다시 시도
          </button>
        </div>
      )}

      {view === 'done' && result && (
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
            {restoredKey && (
              <p className="hint">앞서 만든 계획을 이어서 보여 드려요. 확인하고 확정해 주세요.</p>
            )}
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
                <b style={{ fontSize: '14px' }}>빈 시간에 {plan.blocks.length}개 배치</b>
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
                지킵니다.
              </p>

              {/* 규칙 위반이 0건이고 놓인 블록이 있을 때만 확정할 수 있다 — 서버도 한 번 더 검사한다 */}
              {violations && violations.length === 0 && plan.blocks.length > 0 && (
                <div className="stack" style={{ gap: 'var(--gap-2)' }}>
                  {saveState.state === 'saved' ? (
                    <p className="hint" style={{ color: 'var(--ok)' }}>
                      계획을 저장했습니다. 위 &apos;내 학습 일정&apos;에서 확인할 수 있어요. 다시 만들면 이전 계획은 보관됩니다.
                    </p>
                  ) : saveState.state === 'login' ? (
                    <div className="stack" style={{ gap: 'var(--gap-2)' }}>
                      <p className="hint">가입하거나 로그인하면 이 계획을 저장할 수 있어요. 만든 계획은 그대로 이어집니다.</p>
                      <div style={{ display: 'flex', gap: 'var(--gap-2)' }}>
                        <Link className="btn btn-primary btn-sm" href="/signup?next=/schedule">회원가입</Link>
                        <Link className="btn btn-sm" href="/login?next=/schedule">로그인</Link>
                      </div>
                    </div>
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
