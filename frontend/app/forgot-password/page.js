'use client';

import Link from 'next/link';
import { useState } from 'react';
import { api } from '@/lib/api';
import { authErrorMessage } from '@/lib/password-feedback';

export default function ForgotPasswordPage() {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState('');
  const [sent, setSent] = useState(false);
  async function submit(event) {
    event.preventDefault();
    if (pending || sent) return;
    const email = event.currentTarget.elements.email.value.trim();
    setPending(true);
    setMessage('');
    try {
      const result = await api.auth.forgotPassword({ email });
      setMessage(result.message);
      setSent(true);
    } catch (error) {
      setMessage(authErrorMessage(error, 'forgot'));
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="focus"><main className="shell page">
      <header style={{ paddingTop: 'var(--gap-5)' }}>
        <h1 style={{ fontSize: 22 }}>비밀번호 재설정</h1>
        <p className="hint">가입한 이메일을 입력하면 새 비밀번호를 설정할 수 있는 링크를 보내드립니다.</p>
      </header>
      <form className="stack" style={{ gap: 'var(--gap-4)' }} onSubmit={submit}>
        <div className="field">
          <label htmlFor="recovery-email">이메일</label>
          <input id="recovery-email" name="email" type="email" className="input" autoComplete="email" required disabled={pending || sent} />
        </div>
        {message && <p role="status">{message}</p>}
        <button className="btn btn-primary" type="submit" disabled={pending || sent}>
          {pending ? '요청 중...' : sent ? '메일함을 확인해 주세요' : '재설정 메일 받기'}
        </button>
        {sent && <>
          <p className="hint">스팸함도 확인해 주세요. 메일이 없으면 잠시 기다린 뒤 주소를 확인하고 다시 요청해 주세요.</p>
          <button className="btn" type="button" onClick={() => { setSent(false); setMessage(''); }}>이메일 수정 또는 다시 요청</button>
        </>}
      </form>
      <Link href="/login" className="accent-text">로그인으로 돌아가기</Link>
    </main></div>
  );
}
