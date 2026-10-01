'use client';

// 내 학습 통계(/study/stats)를 읽는 훅 — 대시보드 · 마이페이지 · 적응형 테마가 같이 쓴다
//
//   status: loading | anon(로그인 필요) | ready | error
//   data:   total_minutes · week_minutes · streak_days · level · level_name · studied_days
//           week_planned_minutes · week_done_minutes · week_rate
//           history [{date, minutes}] (최근 20주, 안 한 날 0) · hours [{label, value}] (시작 시각대별 횟수)
// 학습을 기록하거나 계획이 바뀌면 notifyPlanChanged() 이벤트로 다시 읽는다 (usePlan 과 같은 신호).

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { api, getToken } from './api';
import { PLAN_CHANGED } from './usePlan';

function subscribeToken(onChange) {
  window.addEventListener('storage', onChange);
  return () => window.removeEventListener('storage', onChange);
}
const tokenOnServer = () => undefined;

// 같은 순간 여러 곳(적응형 테마 + 페이지)이 부르면 요청 하나를 나눠 쓴다.
// 동시에 두 번 보내면 서버가 같은 계산을 두 번 하고, 화면마다 결과 도착 순서가 달라진다.
const SHARE_MS = 2000;
let shared = null; // { token, at, promise }

function loadStats(token) {
  const now = Date.now();
  if (shared && shared.token === token && now - shared.at < SHARE_MS) return shared.promise;
  const promise = api.study.stats();
  shared = { token, at: now, promise };
  promise.catch(() => {
    if (shared?.promise === promise) shared = null; // 실패한 요청은 나눠 쓰지 않는다
  });
  return promise;
}

export function useStats() {
  const token = useSyncExternalStore(subscribeToken, getToken, tokenOnServer);
  const [version, setVersion] = useState(0);
  const [state, setState] = useState({ status: 'loading', data: null, error: '' });

  const reload = useCallback(() => {
    shared = null; // 기록·계획이 바뀌었으니 나눠 쓰던 결과는 버린다
    setVersion((v) => v + 1);
  }, []);

  useEffect(() => {
    window.addEventListener(PLAN_CHANGED, reload);
    return () => window.removeEventListener(PLAN_CHANGED, reload);
  }, [reload]);

  useEffect(() => {
    if (!token) return undefined;
    let alive = true;
    loadStats(token).then(
      (data) => alive && setState({ status: 'ready', data, error: '' }),
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

  if (token === undefined) return { status: 'loading', data: null, error: '', reload };
  if (!token) return { status: 'anon', data: null, error: '', reload };
  return { ...state, reload };
}
