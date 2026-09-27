'use client';

// 진행 중 계획(/plan/active)을 읽는 훅 — 담당 C
//
// 목표는 동시에 최대 2개(FR-GOAL-07)라 계획도 여러 개다.
//   status: loading | anon(로그인 필요) | empty(확정한 계획 없음) | ready | error
//   plans:  계획 목록 (최근 것부터). 각 계획에 slot(0·1) — 화면에서 목표를 구분하는 색 번호
//   blocks: 모든 계획의 블록을 한데 모은 것. 블록마다 plan_id · goal_title · deadline · slot 이 붙는다
// 계획을 확정하거나 블록을 끝내면 notifyPlanChanged() 로 알린다 → 이 훅을 쓰는 화면이 다시 읽는다.

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { api, getToken } from './api';

export const PLAN_CHANGED = 'sp:plan-changed';

export function notifyPlanChanged() {
  window.dispatchEvent(new Event(PLAN_CHANGED));
}

// 로그인 토큰은 다른 탭에서 바뀔 수 있다 (storage 이벤트)
function subscribeToken(onChange) {
  window.addEventListener('storage', onChange);
  return () => window.removeEventListener('storage', onChange);
}
const tokenOnServer = () => undefined;

const EMPTY = { plans: [], blocks: [], maxPlans: 2 };

export function usePlan() {
  const token = useSyncExternalStore(subscribeToken, getToken, tokenOnServer);
  const [version, setVersion] = useState(0);
  const [state, setState] = useState({ status: 'loading', data: null, error: '' });

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    window.addEventListener(PLAN_CHANGED, reload);
    return () => window.removeEventListener(PLAN_CHANGED, reload);
  }, [reload]);

  useEffect(() => {
    if (!token) return undefined;
    let alive = true;
    api.plan.active().then(
      (data) => alive && setState({ status: data.plans.length ? 'ready' : 'empty', data, error: '' }),
      (err) => {
        if (!alive) return;
        const anon = err.status === 401 || err.status === 403;
        setState({ status: anon ? 'anon' : 'error', data: null, error: err.message });
      },
    );
    return () => {
      alive = false;
    };
  }, [token, version]);

  const view = useMemo(() => {
    if (!state.data) return EMPTY;
    // 먼저 만든 목표가 0번 색을 갖는다 — 새 목표를 더해도 기존 목표 색이 바뀌지 않게
    const plans = [...state.data.plans].reverse().map((p, slot) => ({ ...p, slot }));
    const blocks = plans.flatMap((p) =>
      p.blocks.map((b) => ({ ...b, plan_id: p.plan_id, goal_title: p.goal_title, deadline: p.deadline, slot: p.slot })),
    );
    return { plans, blocks, maxPlans: state.data.max_plans };
  }, [state.data]);

  if (token === undefined) return { status: 'loading', ...EMPTY, error: '', reload };
  if (!token) return { status: 'anon', ...EMPTY, error: '', reload };
  return { status: state.status, ...view, error: state.error, reload };
}
