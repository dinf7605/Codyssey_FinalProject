'use client';

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { api, getToken } from '@/lib/api';
import { notifyPlanChanged, usePlan } from '@/lib/usePlan';
import { dayKey, hhmm, kstIso, kstToday } from '@/lib/planView';

// FR-STUDY-01 학습 타이머 / FR-STUDY-02 블록 완료 / FR-STUDY-05 메모 / FR-STUDY-03·04 집계 표시 (담당 C)
//
// - 5분 미만은 기록하지 않는다
// - 브라우저를 닫아도 마지막 시각까지 남는다 (기기에 저장 → 다시 열면 멈춘 상태로 이어서)
// - 30분 동안 조작이 없으면 멈추고 묻는다 — 자리를 비운 시간까지 공부로 세지 않으려고
// - 오프라인이면 기기에 모아 두었다가 다시 연결되면 보낸다

const DRAFT_KEY = 'sp_study_timer';
const QUEUE_KEY = 'sp_study_pending';
const MIN_SECONDS = 5 * 60;
const IDLE_MS = 30 * 60 * 1000;

function readJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    if (value == null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 저장소를 못 쓰는 환경이면 새로고침 때 이어하기만 안 된다 */
  }
}

// 닫기 직전까지 흐른 시간을 더해서, 멈춘 상태로 되살린다
function restoreDraft() {
  if (typeof window === 'undefined') return null;
  const d = readJson(DRAFT_KEY, null);
  if (!d) return null;
  const ran = d.runStart ? Math.max(0, (d.savedAt - d.runStart) / 1000) : 0;
  return { blockId: d.blockId ?? null, accum: d.accum + ran, runStart: null };
}

// 이벤트 처리기에서만 부른다. (lint 가 처리기 안의 Date.now 를 렌더링 중 호출로 오인해 막는다)
const nowMs = () => Date.now();

const elapsed = (timer, at) => (timer ? timer.accum + (timer.runStart ? (at - timer.runStart) / 1000 : 0) : 0);

// fetch 자체가 실패하면(오프라인) status 가 없다
const isOffline = (err) => !err.status;
const needsLogin = (err) => err.status === 401 || err.status === 403;

async function flushQueue() {
  const queue = readJson(QUEUE_KEY, []);
  if (!queue.length || !getToken()) return 0;
  const left = [];
  let sent = 0;
  for (const record of queue) {
    try {
      await api.study.record(record);
      sent += 1;
    } catch (err) {
      // 서버가 내용을 거절한 것은 다시 보내도 같다 — 연결·로그인 문제만 남겨 둔다
      if (isOffline(err) || needsLogin(err)) left.push(record);
    }
  }
  writeJson(QUEUE_KEY, left);
  return sent;
}

function format(sec) {
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const r = String(s % 60).padStart(2, '0');
  return h ? `${h}:${m}:${r}` : `${m}:${r}`;
}

function hoursText(minutes) {
  const h = Math.floor(minutes / 60);
  return h ? `${h}시간 ${minutes % 60}분` : `${minutes}분`;
}

const subscribeNothing = () => () => {};
const useMounted = () => useSyncExternalStore(subscribeNothing, () => true, () => false);

export default function StudyTimer({ blockId = null }) {
  const mounted = useMounted();
  const { status, plan } = usePlan();
  const [timer, setTimer] = useState(restoreDraft); // {blockId, accum(초), runStart(ms|null)} | null
  const [now, setNow] = useState(() => Date.now());
  const [idleSeconds, setIdleSeconds] = useState(0);
  const [note, setNote] = useState('');
  const [result, setResult] = useState(null);
  const [stats, setStats] = useState(null);
  const [flushed, setFlushed] = useState(0);
  const lastActive = useRef(0);

  const running = Boolean(timer?.runStart);
  const seconds = elapsed(timer, now);

  // 진행 중 타이머가 있으면 그 블록, 아니면 주소의 블록, 아니면 오늘 남은 첫 블록
  const today = kstToday();
  const blocks = plan?.blocks || [];
  const wanted = timer ? timer.blockId : blockId;
  const block = wanted
    ? blocks.find((b) => b.id === wanted) || null
    : blocks.filter((b) => !b.done && dayKey(b.start) === today).sort((a, b) => a.start.localeCompare(b.start))[0] || null;
  const otherRequested = timer && blockId && blockId !== timer.blockId;

  const loadStats = useCallback(() => {
    if (!getToken()) return;
    api.study.stats().then(setStats, () => {});
  }, []);

  useEffect(() => {
    loadStats();
    const send = () =>
      flushQueue().then((n) => {
        if (!n) return;
        setFlushed(n);
        notifyPlanChanged();
        loadStats();
      });
    send();
    window.addEventListener('online', send);
    return () => window.removeEventListener('online', send);
  }, [loadStats]);

  // 조작 = 누르기·키 입력·스크롤. 탭으로 돌아온 것만으로는 조작으로 치지 않는다
  useEffect(() => {
    const touch = () => {
      lastActive.current = Date.now();
    };
    const events = ['pointerdown', 'keydown', 'wheel', 'touchstart'];
    events.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    return () => events.forEach((e) => window.removeEventListener(e, touch));
  }, []);

  useEffect(() => {
    if (!running) return undefined;
    const id = setInterval(() => {
      const t = nowMs();
      setNow(t);
      if (t - lastActive.current > IDLE_MS) {
        setTimer((prev) => (prev?.runStart ? { ...prev, accum: elapsed(prev, t), runStart: null } : prev));
        setIdleSeconds(Math.floor((t - lastActive.current) / 1000));
      }
    }, 1000);
    return () => clearInterval(id);
  }, [running]);

  // 1초마다 기기에 남긴다 — 브라우저를 닫아도 마지막 시각까지 기록된다
  useEffect(() => {
    if (mounted) writeJson(DRAFT_KEY, timer ? { ...timer, savedAt: now } : null);
  }, [mounted, timer, now]);

  function start() {
    const t = nowMs();
    lastActive.current = t;
    setNow(t);
    setIdleSeconds(0);
    setResult(null);
    // 계획을 아직 못 읽었어도 주소로 고른 블록은 놓치지 않는다
    setTimer((prev) => (prev ? { ...prev, runStart: t } : { blockId: block?.id ?? wanted ?? null, accum: 0, runStart: t }));
  }

  function pause() {
    const t = nowMs();
    setNow(t);
    setTimer((prev) => ({ ...prev, accum: elapsed(prev, t), runStart: null }));
  }

  function dropIdle() {
    setTimer((prev) => ({ ...prev, accum: Math.max(0, prev.accum - idleSeconds) }));
    setIdleSeconds(0);
  }

  function reset() {
    setTimer(null);
    setNote('');
    setIdleSeconds(0);
    setResult(null);
  }

  function complete() {
    const t = nowMs();
    const active = Math.floor(elapsed(timer, t));
    setNow(t);
    setTimer((prev) => ({ ...prev, accum: active, runStart: null }));
    setIdleSeconds(0);

    // 일시정지한 시간은 빼고 순수 학습시간만 남긴다 — 서버는 끝-시작으로 분을 잰다
    const record = {
      blockId: timer.blockId,
      startedAt: kstIso(t - active * 1000),
      endedAt: kstIso(t),
      expectedMinutes: block?.minutes ?? null,
      note: note.trim() || null,
    };

    if (!getToken()) {
      setResult({ state: 'login' });
      return;
    }
    setResult({ state: 'saving' });
    submit(record);
  }

  async function submit(record) {
    try {
      const res = await api.study.record(record);
      setTimer(null);
      setNote('');
      setResult({ state: 'saved', res, blockId: record.blockId });
      notifyPlanChanged();
      loadStats();
    } catch (err) {
      if (isOffline(err)) {
        writeJson(QUEUE_KEY, [...readJson(QUEUE_KEY, []), record]);
        setTimer(null);
        setNote('');
        setResult({ state: 'queued' });
      } else if (needsLogin(err)) {
        setResult({ state: 'login' });
      } else {
        setResult({ state: 'error', message: err.message });
      }
    }
  }

  // FR-STUDY-02 — 방금 한 완료는 24시간 안에 취소할 수 있다
  async function cancelDone(id) {
    try {
      await api.study.cancelDone(id);
      setResult({ state: 'cancelled' });
      notifyPlanChanged();
    } catch (err) {
      setResult({ state: 'error', message: err.message });
    }
  }

  if (!mounted) {
    return <p className="hint">타이머를 준비하는 중…</p>;
  }

  const tooShort = seconds < MIN_SECONDS;
  const saving = result?.state === 'saving';

  return (
    <>
      <header className="stack" style={{ gap: 4 }}>
        <h1 style={{ fontSize: 20 }}>학습</h1>
        <p className="muted tiny">
          {block
            ? `${block.title} · ${Number(block.start.slice(5, 7))}/${Number(block.start.slice(8, 10))} ${hhmm(block.start)}~${hhmm(block.end)}`
            : status === 'loading'
              ? '계획을 불러오는 중…'
              : wanted && status === 'ready'
                ? '고른 블록을 계획에서 찾지 못했어요 — 시간만 기록합니다'
                : '자유 학습 — 계획 블록 없이 시간만 기록합니다'}
        </p>
        {status === 'anon' && (
          <p className="hint">
            로그인하지 않아도 타이머는 쓸 수 있어요. 기록은 <Link href="/login?next=/study">로그인</Link> 후 저장됩니다.
          </p>
        )}
        {block?.done && !timer && (
          <p className="hint">이미 완료한 블록이에요. 다시 재면 추가 학습 시간으로 기록됩니다.</p>
        )}
        {otherRequested && (
          <p className="hint">진행 중인 타이머가 있어 그 블록을 먼저 보여 줍니다. 완료하거나 초기화하면 고른 블록으로 넘어갑니다.</p>
        )}
      </header>

      <section className="panel" style={{ padding: 'var(--gap-6) var(--gap-4)' }}>
        <p className="timer" role="timer" aria-live="off">{format(seconds)}</p>
        {block && (
          <p className="dim tiny" style={{ textAlign: 'center', marginTop: 6 }}>
            예상 {block.minutes}분
          </p>
        )}

        <div style={{ display: 'flex', gap: 'var(--gap-2)', marginTop: 'var(--gap-5)' }}>
          <button
            type="button"
            className={running ? 'btn' : 'btn btn-primary'}
            onClick={running ? pause : start}
            disabled={saving}
          >
            {running ? '일시정지' : seconds === 0 ? '시작' : '이어서'}
          </button>
          <button type="button" className="btn" disabled={tooShort || saving} onClick={complete}>
            {saving ? '기록하는 중…' : '완료'}
          </button>
        </div>

        {tooShort && seconds > 0 && (
          <p className="hint" style={{ marginTop: 'var(--gap-3)', textAlign: 'center' }}>
            5분 이상 학습해야 기록됩니다
          </p>
        )}
        {!running && seconds > 0 && !saving && (
          <p style={{ marginTop: 'var(--gap-2)', textAlign: 'center' }}>
            <button type="button" className="btn btn-quiet btn-sm" onClick={reset}>기록하지 않고 초기화</button>
          </p>
        )}
      </section>

      {idleSeconds > 0 && timer && (
        <section className="progress" role="alertdialog" aria-label="자동 일시정지">
          <b>30분 넘게 조작이 없어 타이머를 멈췄어요</b>
          <p className="muted tiny">
            계속 공부하고 계셨나요? 자리를 비웠다면 마지막 조작 뒤 {Math.round(idleSeconds / 60)}분은 빼고 기록할 수 있어요.
          </p>
          <div style={{ display: 'flex', gap: 'var(--gap-2)' }}>
            <button type="button" className="btn btn-sm" onClick={() => setIdleSeconds(0)}>네, 모두 기록</button>
            <button type="button" className="btn btn-sm" onClick={dropIdle}>비운 시간 빼기</button>
          </div>
        </section>
      )}

      {result?.state === 'saved' && (
        <p className="hint" style={{ color: 'var(--ok)' }} role="status">
          {result.res.minutes}분을 기록했어요
          {result.res.deviation_percent != null &&
            ` · 예상보다 ${result.res.deviation_percent >= 0 ? '+' : ''}${result.res.deviation_percent}%`}
          {result.res.block_done ? ' · 블록을 완료로 표시했어요.' : '.'} <Link href="/schedule">일정 보기</Link>
          {result.res.block_done && result.blockId && (
            <>
              {' · '}
              <button type="button" className="btn-link" onClick={() => cancelDone(result.blockId)}>
                완료 취소
              </button>
            </>
          )}
        </p>
      )}
      {result?.state === 'cancelled' && (
        <p className="hint" role="status">완료를 취소했어요. 공부한 시간 기록은 그대로 남아요.</p>
      )}
      {result?.state === 'queued' && (
        <p className="hint" role="status">연결이 끊겨 기기에 저장했어요. 다시 연결되면 자동으로 보냅니다.</p>
      )}
      {result?.state === 'login' && (
        <p className="hint" role="status">
          기록하려면 로그인이 필요해요. 타이머는 이 기기에 남아 있으니 <Link href="/login?next=/study">로그인</Link> 후 다시 완료를 누르세요.
        </p>
      )}
      {result?.state === 'error' && (
        <p className="hint" style={{ color: 'var(--late)' }} role="alert">{result.message}</p>
      )}
      {flushed > 0 && (
        <p className="hint" role="status">연결이 끊겼을 때 저장한 기록 {flushed}건을 보냈어요.</p>
      )}

      <section>
        <div className="sec-head">
          <h2>학습 메모</h2>
          <span className="dim tiny">{note.length}/200 · 선택</span>
        </div>
        <div className="field">
          <textarea
            className="input"
            rows={3}
            maxLength={200}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="오늘 이해가 안 된 부분을 200자까지 남길 수 있어요"
            style={{ minHeight: 88, padding: 'var(--gap-3)', resize: 'vertical' }}
          />
          <p className="hint">메모를 비워도 완료 처리에는 영향이 없습니다</p>
        </div>
      </section>

      {stats && (
        <section className="rows" aria-label="내 학습 집계">
          <div className="row">
            <div className="row-main">
              <b>Lv.{stats.level} {stats.level_name}</b>
              <span>누적 {hoursText(stats.total_minutes)} · 이번 주 {hoursText(stats.week_minutes)}</span>
            </div>
            <span className="pill">{stats.streak_days}일 연속</span>
          </div>
          {stats.week_rate != null && (
            <div className="row">
              <div className="row-main">
                <b>이번 주 달성률 {stats.week_rate}%</b>
                <span>
                  계획 {hoursText(stats.week_planned_minutes)} 중 완료 {hoursText(stats.week_done_minutes)}
                </span>
              </div>
              <div className="bar" style={{ width: 80 }} aria-hidden="true">
                <div className="bar-fill" style={{ width: `${Math.min(100, stats.week_rate)}%` }} />
              </div>
            </div>
          )}
        </section>
      )}
    </>
  );
}
