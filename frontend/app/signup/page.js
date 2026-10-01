'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import GoogleLoginButton from '@/components/GoogleLoginButton';
import { api } from '@/lib/api';
import { loadExploration } from '@/lib/goalSession';
import SignupConsentFields from '@/components/SignupConsentFields';
import PasswordFields from '@/components/PasswordFields';
import { passwordValid, authErrorMessage } from '@/lib/password-feedback';

// FR-JOIN-01 정보 입력 / FR-JOIN-02 개인정보 수집 동의 / FR-JOIN-03 AI 이용 고지
// 필수 동의 2개를 체크해야 가입 버튼이 활성화된다.

export default function SignupPage() {
  const router = useRouter();
  const [privacy, setPrivacy] = useState(false);
  const [aiNotice, setAiNotice] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [nickname, setNickname] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState('');

  async function submit(event) {
    event.preventDefault();
    if (pending) return;
    if (!privacy || !aiNotice) {
      setMessage('개인정보 수집·이용 및 AI 이용 안내의 필수 항목에 동의해 주세요.');
      return;
    }
    const trimmedEmail = email.trim();
    const trimmedNickname = nickname.trim();
    if (!passwordValid(password)) {
      setMessage('비밀번호는 8~64자로 영문·숫자·특수문자를 포함해야 합니다.');
      return;
    }
    if (!passwordValid(password, { email: trimmedEmail, nickname: trimmedNickname })) {
      setMessage('비밀번호에 이메일 아이디나 닉네임을 넣을 수 없습니다.');
      return;
    }
    if (password !== confirmation) {
      setMessage('비밀번호 확인이 일치하지 않습니다.');
      return;
    }
    if (trimmedNickname.length < 2 || trimmedNickname.length > 10) {
      setMessage('닉네임은 2~10자로 입력해 주세요.');
      return;
    }
    setPending(true);
    setMessage('');
    try {
      await api.auth.signup({
        email: trimmedEmail, password, nickname: trimmedNickname,
        agreePrivacy: privacy, agreeAiNotice: aiNotice,
        agreeMarketing: marketing,
      });
      loadExploration(); // 30분 내 목표 탐색 정보는 로그인 뒤에도 유지된다.
      setMessage('가입 요청이 완료되었습니다. 인증 메일이 왔다면 확인한 뒤 로그인해 주세요.');
      const next = new URLSearchParams(window.location.search).get('next');
      const login = next && /^\/(?![/\\])/.test(next)
        ? `/login?next=${encodeURIComponent(next)}` : '/login';
      setTimeout(() => router.push(login), 1500);
    } catch (error) {
      setMessage(authErrorMessage(error, 'signup'));
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="focus">
    <main className="shell page">
      <header style={{ paddingTop: 'var(--gap-5)' }}>
        <h1 style={{ fontSize: 22 }}>회원가입</h1>
        <p className="muted tiny" style={{ marginTop: 6 }}>
          방금 고른 목표와 가용 시간을 그대로 이어받습니다
        </p>
      </header>

      <form className="stack" style={{ gap: 'var(--gap-4)' }} onSubmit={submit}>
        <div className="field">
          <label htmlFor="su-email">이메일</label>
          <input id="su-email" name="email" type="email" className="input" autoComplete="email" required
            value={email} onChange={(event) => setEmail(event.target.value)} />
        </div>

        <PasswordFields
          idPrefix="su" password={password} confirmation={confirmation}
          onPasswordChange={setPassword} onConfirmationChange={setConfirmation}
          disabled={pending} personal={{ email, nickname }}
        />

        <div className="field">
          <label htmlFor="su-nick">닉네임</label>
          <input id="su-nick" name="nickname" type="text" className="input" minLength={2} maxLength={10} placeholder="2~10자" required
            value={nickname} onChange={(event) => setNickname(event.target.value)} />
        </div>

        <SignupConsentFields
          privacy={privacy}
          onPrivacyChange={setPrivacy}
          aiNotice={aiNotice}
          onAiNoticeChange={setAiNotice}
          marketing={marketing}
          onMarketingChange={setMarketing}
          disabled={pending}
        />

        {message && <p role="status">{message}</p>}
        <button type="submit" className="btn btn-yellow signup-submit" disabled={!privacy || !aiNotice || pending}>
          {pending ? '가입 중...' : '가입하고 일정 만들기'}
        </button>
        <p className="hint" style={{ textAlign: 'center' }}>
          필수 항목에 동의하면 버튼이 활성화됩니다
        </p>
      </form>

      <GoogleLoginButton label="구글 계정으로 가입하기" />

      <p style={{ textAlign: 'center', fontSize: '14px' }}>
        이미 계정이 있나요? <Link href="/login" className="accent-text">로그인</Link>
      </p>
    </main>
    </div>
  );
}
