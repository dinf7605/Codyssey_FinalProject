'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { api, clearAuthTokens } from '@/lib/api';
import PasswordFields from '@/components/PasswordFields';
import { passwordValid, authErrorMessage } from '@/lib/password-feedback';
import { parseRecoveryLink } from '@/lib/recovery-link';

export default function ResetPasswordPage() {
  const credentials = useRef(undefined);
  const [linkState, setLinkState] = useState('loading');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => {
    // 메일 토큰은 메모리에만 보관하고 주소창에서는 즉시 지운다.
    // StrictMode 재실행에서도 처음 읽은 값을 유지한다.
    if (credentials.current === undefined) {
      credentials.current = parseRecoveryLink(window.location.hash);
      window.history.replaceState(window.history.state, '', window.location.pathname);
    }
    let active = true;
    queueMicrotask(() => {
      if (active) setLinkState(credentials.current ? 'ready' : 'invalid');
    });
    return () => { active = false; };
  }, []);
  async function submit(event) {
    event.preventDefault();
    if (pending || done || !credentials.current) return;
    if (!passwordValid(password)) {
      setMessage('비밀번호는 8~64자로 영문·숫자·특수문자를 포함해야 합니다.');
      return;
    }
    if (password !== confirmation) { setMessage('비밀번호 확인이 일치하지 않습니다.'); return; }
    setPending(true);
    setMessage('');
    try {
      const result = await api.auth.resetPassword({ ...credentials.current, newPassword: password });
      credentials.current = null;
      setPassword('');
      setConfirmation('');
      setDone(true);
      setMessage(result.message);
      // 성공 응답 이후 로컬 저장소 접근 실패가 비밀번호 변경 실패로 표시되지 않게 한다.
      try { clearAuthTokens(); } catch { /* 저장소가 차단된 브라우저 */ }
    } catch (error) {
      setMessage(authErrorMessage(error, 'reset'));
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="focus"><main className="shell page">
      <header style={{ paddingTop: 'var(--gap-5)' }}><h1 style={{ fontSize: 22 }}>새 비밀번호 설정</h1></header>
      {linkState === 'loading' && <p role="status">재설정 링크를 확인하고 있습니다.</p>}
      {linkState === 'invalid' && <p role="alert">유효한 재설정 링크가 없습니다. 메일에서 링크를 다시 열거나 새 메일을 요청해 주세요.</p>}
      {linkState === 'ready' && !done && <form className="stack" style={{ gap: 'var(--gap-4)' }} onSubmit={submit}>
        <PasswordFields idPrefix="reset" label="새 비밀번호" password={password} confirmation={confirmation}
          onPasswordChange={setPassword} onConfirmationChange={setConfirmation} disabled={pending} />
        {message && <p role="status">{message}</p>}
        <button className="btn btn-primary" type="submit" disabled={pending}>{pending ? '변경 중...' : '비밀번호 변경'}</button>
      </form>}
      {done && <p role="status">{message}</p>}
      {!done && <Link href="/forgot-password" className="accent-text">재설정 메일 다시 요청</Link>}
      <Link href="/login" className="accent-text">로그인으로 돌아가기</Link>
    </main></div>
  );
}
