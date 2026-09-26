'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { loadExploration } from '@/lib/goalSession';

// FR-JOIN-01 정보 입력 / FR-JOIN-02 개인정보 수집 동의 / FR-JOIN-03 AI 이용 고지
// 필수 동의 2개를 체크해야 가입 버튼이 활성화된다.

export default function SignupPage() {
  const router = useRouter();
  const [privacy, setPrivacy] = useState(false);
  const [aiNotice, setAiNotice] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState('');

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const email = form.elements.email.value.trim();
    const password = form.elements.password.value;
    const nickname = form.elements.nickname.value.trim();
    if (!/^(?=.{8,64}$)(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d]).+$/.test(password)) {
      setMessage('비밀번호는 8~64자로 영문·숫자·특수문자를 포함해야 합니다.');
      return;
    }
    if (nickname.length < 2 || nickname.length > 10) {
      setMessage('닉네임은 2~10자로 입력해 주세요.');
      return;
    }
    setPending(true);
    setMessage('');
    try {
      await api.auth.signup({
        email, password, nickname,
        agreePrivacy: privacy, agreeAiNotice: aiNotice,
        agreeMarketing: form.elements.marketing.checked,
      });
      loadExploration(); // 30분 내 목표 탐색 정보는 로그인 뒤에도 유지된다.
      setMessage('가입 요청이 완료되었습니다. 인증 메일이 왔다면 확인한 뒤 로그인해 주세요.');
      setTimeout(() => router.push('/login'), 1500);
    } catch (error) {
      setMessage(error.status ? '가입하지 못했습니다. 입력한 정보를 확인하고 다시 시도해 주세요.' : '서버에 연결할 수 없습니다. 백엔드 실행 상태를 확인해 주세요.');
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
          <input id="su-email" name="email" type="email" className="input" autoComplete="email" required />
        </div>

        <div className="field">
          <label htmlFor="su-pw">비밀번호</label>
          <input id="su-pw" name="password" type="password" className="input" autoComplete="new-password" required minLength={8} maxLength={64} />
          <p className="hint">8~64자 · 영문, 숫자, 특수문자를 각각 1자 이상 포함</p>
        </div>

        <div className="field">
          <label htmlFor="su-nick">닉네임</label>
          <input id="su-nick" name="nickname" type="text" className="input" minLength={2} maxLength={10} placeholder="2~10자" required />
        </div>

        <fieldset className="panel" style={{ padding: 'var(--gap-4)', display: 'flex', flexDirection: 'column', gap: 'var(--gap-3)' }}>
          <legend className="tiny strong" style={{ padding: '0 6px' }}>약관 동의</legend>

          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13 }}>
            <input type="checkbox" checked={privacy} onChange={(event) => setPrivacy(event.target.checked)} style={{ marginTop: 3 }} />
            <span>
              <b>[필수]</b> 개인정보 수집·이용 동의
              <br />
              <span className="dim tiny">
                이메일, 학습 이력, 캘린더 시간대를 수집합니다. 일정 제목과 참석자는 저장하지 않습니다.
              </span>
            </span>
          </label>

          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13 }}>
            <input type="checkbox" checked={aiNotice} onChange={(event) => setAiNotice(event.target.checked)} style={{ marginTop: 3 }} />
            <span>
              <b>[필수]</b> AI 생성 콘텐츠 고지 확인
              <br />
              <span className="dim tiny">
                추천 목표와 학습 일정은 AI가 생성하며 부정확할 수 있습니다.
              </span>
            </span>
          </label>

          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13 }}>
            <input type="checkbox" name="marketing" style={{ marginTop: 3 }} />
            <span><b className="muted">[선택]</b> 학습 알림 메일 수신</span>
          </label>
        </fieldset>

        {message && <p role="status">{message}</p>}
        <button type="submit" className="btn btn-primary" disabled={!privacy || !aiNotice || pending}>
          {pending ? '가입 중...' : '가입하고 일정 만들기'}
        </button>
        <p className="hint" style={{ textAlign: 'center' }}>
          필수 항목에 동의하면 버튼이 활성화됩니다
        </p>
      </form>

      <p style={{ textAlign: 'center', fontSize: 13 }}>
        이미 계정이 있나요? <Link href="/login" className="accent-text">로그인</Link>
      </p>
    </main>
    </div>
  );
}
