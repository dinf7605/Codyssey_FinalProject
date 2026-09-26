'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, setAuthTokens } from '@/lib/api';
import { loadExploration } from '@/lib/goalSession';

// FR-AUTH-01 이메일 로그인 / FR-AUTH-02 구글 로그인 / FR-AUTH-03 비밀번호 재설정
// 실패 문구는 '아이디 또는 비밀번호가 올바르지 않습니다'로 통일한다 (NFR-SEC-01).
// 비밀번호 조합 규칙은 이 화면에 노출하지 않는다 — 정책 힌트가 된다.

export default function LoginPage() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setPending(true);
    setError('');
    const form = event.currentTarget;
    try {
      const result = await api.auth.login({
        email: form.elements.email.value.trim(),
        password: form.elements.password.value,
      });
      setAuthTokens({
        accessToken: result.access_token,
        refreshToken: result.refresh_token,
        userId: result.user_id,
      });
      loadExploration(); // 온보딩 입력은 일정 화면에서도 읽을 수 있도록 보존한다.
      router.push('/schedule');
    } catch (err) {
      setError(err.status === 401 ? '이메일 또는 비밀번호가 틀렸습니다.' : '로그인에 실패했습니다. 서버 연결을 확인해 주세요.');
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="focus">
    <main className="shell page">
      <header style={{ paddingTop: 'var(--gap-5)' }}>
        <h1 style={{ fontSize: 22 }}>로그인</h1>
        <p className="muted tiny" style={{ marginTop: 6 }}>
          학습 일정과 진도를 이어서 관리합니다
        </p>
      </header>

      <form className="stack" style={{ gap: 'var(--gap-4)' }} onSubmit={submit}>
        <div className="field">
          <label htmlFor="email">이메일</label>
          <input id="email" name="email" type="email" className="input" autoComplete="email" placeholder="you@example.com" required />
        </div>

        <div className="field">
          <label htmlFor="password">비밀번호</label>
          <input id="password" name="password" type="password" className="input" autoComplete="current-password" required />
        </div>

        {error && <p role="alert" style={{ color: 'red' }}>{error}</p>}
        <button type="submit" className="btn btn-primary" disabled={pending}>{pending ? '로그인 중...' : '로그인'}</button>
        <button type="button" className="btn" disabled>구글 계정으로 계속하기 (준비 중)</button>

        <p className="hint" style={{ textAlign: 'center' }}>
          캘린더 접근 권한은 로그인 단계에서 요구하지 않습니다
        </p>
      </form>

      <div style={{ display: 'flex', justifyContent: 'center', gap: 'var(--gap-4)', fontSize: 13 }}>
        <Link href="/signup" className="accent-text">회원가입</Link>
        <span className="muted">비밀번호 재설정</span>
      </div>
    </main>
    </div>
  );
}
