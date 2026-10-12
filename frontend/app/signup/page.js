'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import GoogleLoginButton from '@/components/GoogleLoginButton';
import { api } from '@/lib/api';
import { loadExploration } from '@/lib/goalSession';
import SignupConsentFields from '@/components/SignupConsentFields';
import PasswordFields from '@/components/PasswordFields';
import ResendConfirmation from '@/components/ResendConfirmation';
import { passwordValid, authErrorMessage } from '@/lib/password-feedback';

// FR-JOIN-01 정보 입력 / FR-JOIN-02 개인정보 수집 동의 / FR-JOIN-03 AI 이용 고지
// 필수 동의 2개를 체크해야 가입 버튼이 활성화된다.

// 가입 뒤 로그인 화면 — 받은 next 는 같은 사이트 안 경로일 때만 넘긴다
function loginHref() {
  const next = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('next');
  return next && /^\/(?![/\\])/.test(next) ? `/login?next=${encodeURIComponent(next)}` : '/login';
}

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
  // 메일 인증이 필요한 가입이면 보낸 주소 — 안내 화면으로 바꾼다. 예전엔 1.5초 뒤 로그인으로 넘어가 안내를 못 봤다 (10-12)
  const [sentTo, setSentTo] = useState('');

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
      const res = await api.auth.signup({
        email: trimmedEmail, password, nickname: trimmedNickname,
        agreePrivacy: privacy, agreeAiNotice: aiNotice,
        agreeMarketing: marketing,
      });
      loadExploration(); // 30분 내 목표 탐색 정보는 로그인 뒤에도 유지된다.
      if (res?.requires_email_confirmation) {
        setSentTo(trimmedEmail);
        window.scrollTo(0, 0);
        return;
      }
      setMessage('가입이 끝났어요. 로그인 화면으로 이동합니다.');
      setTimeout(() => router.push(loginHref()), 1500);
    } catch (error) {
      setMessage(authErrorMessage(error, 'signup'));
    } finally {
      setPending(false);
    }
  }
  if (sentTo) {
    return (
      <div className="focus">
      <main className="shell page">
        <section className="panel stack" style={{ gap: 'var(--gap-4)', marginTop: 'var(--gap-5)', padding: 'var(--gap-5) var(--gap-4)' }} role="status" aria-live="polite">
          <h1 style={{ fontSize: 22 }}>인증 메일을 보냈어요</h1>
          <p style={{ margin: 0 }}>
            <b>{sentTo}</b>(으)로 가입 인증 메일을 보냈습니다. 메일 안의 <b>인증 링크</b>를 누르면 가입이 끝나고 로그인할 수 있어요.
          </p>
          <ul className="hint" style={{ margin: 0, paddingLeft: 18 }}>
            <li>메일이 보이지 않으면 스팸함 · 프로모션함을 확인해 주세요. 도착까지 몇 분 걸릴 수 있어요.</li>
            <li>인증하기 전에는 로그인되지 않아요.</li>
            <li>주소를 잘못 적었다면 다시 가입해 주세요.</li>
          </ul>
          <Link href={loginHref()} className="btn btn-primary">인증했어요, 로그인하기</Link>
          <ResendConfirmation email={sentTo} />
        </section>
      </main>
      </div>
    );
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
