'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import api, { setAuthTokens } from '@/lib/api';

// FR-AUTH-01 이메일 로그인 / FR-AUTH-02 구글 로그인 / FR-AUTH-03 비밀번호 재설정
// 실패 문구는 백엔드 auth.py의 LOGIN_FAILED 문구를 사용한다.

export default function LoginPage() {
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();

    setError('');
    setLoading(true);

    try {
      const data = await api.auth.login({
        email,
        password,
      });

      setAuthTokens({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        userId: data.user_id,
      });

      router.push('/dashboard');
    } catch (err) {
      setError(err.message || '이메일 또는 비밀번호가 틀렸습니다.');
    } finally {
      setLoading(false);
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

        <form className="stack" style={{ gap: 'var(--gap-4)' }} onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="email">이메일</label>
            <input
              id="email"
              name="email"
              type="email"
              className="input"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="password">비밀번호</label>
            <input
              id="password"
              name="password"
              type="password"
              className="input"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <p className="hint" style={{ color: 'var(--danger, #d33)' }}>
              {error}
            </p>
          )}

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '로그인 중...' : '로그인'}
          </button>

          <button type="button" className="btn" disabled>
            구글 계정으로 계속하기
          </button>

          <p className="hint" style={{ textAlign: 'center' }}>
            캘린더 접근 권한은 로그인 단계에서 요구하지 않습니다
          </p>
        </form>

        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            gap: 'var(--gap-4)',
            fontSize: 13,
          }}
        >
          <Link href="/signup" className="accent-text">
            회원가입
          </Link>
          <span className="muted">비밀번호 재설정</span>
        </div>
      </main>
    </div>
  );
}