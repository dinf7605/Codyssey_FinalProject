'use client';

// 진행 중 계획(/plan/current)을 읽는 훅 — 담당 C
//
// status: loading | anon(로그인 필요) | empty(확정한 계획 없음) | ready | error
// 계획을 확정하거나 블록을 끝내면 notifyPlanChanged() 로 알린다 → 이 훅을 쓰는 화면이 다시 읽는다.

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
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

export function usePlan() {
  const token = useSyncExternalStore(subscribeToken, getToken, tokenOnServer);
  const [version, setVersion] = useState(0);
  const [state, setState] = useState({ status: 'loading', plan: null, error: '' });

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    window.addEventListener(PLAN_CHANGED, reload);
    return () => window.removeEventListener(PLAN_CHANGED, reload);
  }, [reload]);

  useEffect(() => {
    if (!token) return undefined;
    let alive = true;
    api.plan.current().then(
      (plan) => alive && setState({ status: plan ? 'ready' : 'empty', plan, error: '' }),
      (err) => {
        if (!alive) return;
        const anon = err.status === 401 || err.status === 403;
        setState({ status: anon ? 'anon' : 'error', plan: null, error: err.message });
      },
    );
    return () => {
      alive = false;
    };
  }, [token, version]);

  if (token === undefined) return { status: 'loading', plan: null, error: '', reload };
  if (!token) return { status: 'anon', plan: null, error: '', reload };
  return { ...state, reload };
}
