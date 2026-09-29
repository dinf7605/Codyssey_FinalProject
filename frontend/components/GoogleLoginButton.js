'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

// FR-AUTH-02 구글로 계속하기 — 로그인·회원가입 화면 공통.
// 돌아올 곳(next)은 이 탭의 세션에 잠깐 두고, 구글에서 돌아온 /auth/callback 이 꺼내 쓴다.
// 캘린더 권한은 여기서 요구하지 않는다 (기본 email·profile 만).

export const GOOGLE_NEXT_KEY = 'sp_google_next';

// '/' 로 시작하되 '//' · '/\' 로 시작하지 않는 우리 사이트 안 경로만 받는다
export function safeNext(value) {
  return value && /^\/(?![/\\])/.test(value) ? value : null;
}

export default function GoogleLoginButton({ next = null, label = '구글 계정으로 계속하기' }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  async function start() {
    setPending(true);
    setError('');
    try {
      const { url } = await api.auth.google.start(`${window.location.origin}/auth/callback`);
      try {
        // 따로 넘기지 않으면 지금 주소의 ?next= (로그인·가입 화면이 받는 값)를 그대로 잇는다
        const target = safeNext(next ?? new URLSearchParams(window.location.search).get('next'));
        if (target) window.sessionStorage.setItem(GOOGLE_NEXT_KEY, target);
        else window.sessionStorage.removeItem(GOOGLE_NEXT_KEY);
      } catch {
        // 저장소가 막혀 있으면 로그인 뒤 기본 화면으로 간다
      }
      window.location.assign(url);
    } catch (err) {
      setError(err.status === 503 ? err.message : '구글 로그인을 시작하지 못했습니다. 서버 연결을 확인해 주세요.');
      setPending(false);
    }
  }

  return (
    <>
      <button type="button" className="btn" onClick={start} disabled={pending}>
        {pending ? '구글로 이동하는 중…' : label}
      </button>
      {error && <p role="alert" className="hint hint-error">{error}</p>}
    </>
  );
}
