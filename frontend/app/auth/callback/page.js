'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { GOOGLE_NEXT_KEY, safeNext } from '@/components/GoogleLoginButton';
import { api, clearAuthTokens, setAuthTokens, tokenOwner } from '@/lib/api';
import { loadExploration } from '@/lib/goalSession';

// FR-AUTH-02 구글 로그인에서 돌아오는 곳 — backend/routers/auth_google.py
// Supabase 가 토큰을 주소의 # 뒤에 붙여 보낸다. 읽자마자 주소창에서 지운다 (기록·공유로 새지 않게).
// 우리 users 프로필이 없는 첫 방문이면 이메일 가입과 같은 필수 동의 2개를 받는다 (FR-JOIN-02/03).

// 대시보드가 실제 계획·기록으로 바뀌어(10-01) 로그인 뒤 첫 화면으로 쓴다 — 계획이 없으면 거기서 목표 정하기로 안내한다
const AFTER_LOGIN = '/dashboard';

// 개발 모드의 StrictMode 는 effect 를 두 번 돌린다. 두 번째에는 이미 지운 주소를 다시 읽지 않도록 한 번만 읽는다.
let captured = null;

function captureTokens() {
  if (captured) return captured;
  const params = new URLSearchParams(window.location.hash.slice(1));
  captured = {
    accessToken: params.get('access_token'),
    refreshToken: params.get('refresh_token'),
    error: params.get('error_description') || params.get('error'),
  };
  window.history.replaceState(null, '', window.location.pathname);
  return captured;
}

function takeNext() {
  try {
    const next = safeNext(window.sessionStorage.getItem(GOOGLE_NEXT_KEY));
    window.sessionStorage.removeItem(GOOGLE_NEXT_KEY);
    return next || AFTER_LOGIN;
  } catch {
    return AFTER_LOGIN;
  }
}

export default function GoogleCallbackPage() {
  const router = useRouter();
  const [state, setState] = useState({ status: 'working', message: '', profile: null, next: AFTER_LOGIN });
  const [privacy, setPrivacy] = useState(false);
  const [aiNotice, setAiNotice] = useState(false);
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      const tokens = captureTokens();
      if (!tokens.accessToken) {
        if (alive) setState((old) => ({ ...old, status: 'error',
          message: tokens.error ? '구글 로그인이 취소되었거나 실패했습니다.' : '로그인 정보를 받지 못했습니다. 다시 시도해 주세요.' }));
        return;
      }
      setAuthTokens({
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
        userId: tokenOwner(tokens.accessToken),
      });
      loadExploration(); // 온보딩 입력은 로그인 뒤에도 이어서 쓴다 (이메일 로그인과 같게)
      const next = takeNext();
      try {
        const profile = await api.auth.google.profile();
        if (!alive) return;
        if (profile.has_profile) {
          router.replace(next);
          return;
        }
        setState({ status: 'consent', message: '', profile, next });
      } catch {
        if (alive) setState((old) => ({ ...old, status: 'error', message: '계정 정보를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.' }));
      }
    })();
    return () => { alive = false; };
  }, [router]);

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const nickname = form.elements.nickname.value.trim();
    if (nickname.length < 2 || nickname.length > 10) {
      setFormError('닉네임은 2~10자로 입력해 주세요.');
      return;
    }
    setPending(true);
    setFormError('');
    try {
      await api.auth.google.complete({
        nickname, agreePrivacy: privacy, agreeAiNotice: aiNotice,
        agreeMarketing: form.elements.marketing.checked,
      });
      router.replace(state.next);
    } catch (error) {
      setFormError(error.status === 401 ? '로그인 시간이 지났습니다. 다시 로그인해 주세요.' : '가입을 마치지 못했습니다. 잠시 후 다시 시도해 주세요.');
      setPending(false);
    }
  }

  function cancel() {
    clearAuthTokens();
    router.replace('/login');
  }

  return (
    <div className="focus">
    <main className="shell page">
      {state.status === 'working' && <p className="hint" role="status" style={{ paddingTop: 'var(--gap-5)' }}>구글 로그인을 확인하고 있습니다…</p>}

      {state.status === 'error' && (
        <section className="stack" style={{ gap: 'var(--gap-3)', paddingTop: 'var(--gap-5)' }}>
          <h1 style={{ fontSize: 20 }}>로그인하지 못했습니다</h1>
          <p role="alert">{state.message}</p>
          <Link href="/login" className="btn btn-primary">로그인 화면으로</Link>
        </section>
      )}

      {state.status === 'consent' && (
        <>
          <header style={{ paddingTop: 'var(--gap-5)' }}>
            <h1 style={{ fontSize: 22 }}>가입 마무리</h1>
            <p className="muted tiny" style={{ marginTop: 6 }}>
              {state.profile.email} 구글 계정으로 처음 오셨어요. 닉네임과 동의만 확인하면 끝납니다.
            </p>
          </header>

          <form className="stack" style={{ gap: 'var(--gap-4)' }} onSubmit={submit}>
            <div className="field">
              <label htmlFor="g-nick">닉네임</label>
              <input id="g-nick" name="nickname" type="text" className="input" minLength={2} maxLength={10}
                defaultValue={state.profile.suggested_nickname} placeholder="2~10자" required />
            </div>

            <fieldset className="panel" style={{ padding: 'var(--gap-4)', display: 'flex', flexDirection: 'column', gap: 'var(--gap-3)' }}>
              <legend className="tiny strong" style={{ padding: '0 6px' }}>약관 동의</legend>

              <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: '14px' }}>
                <input type="checkbox" checked={privacy} onChange={(event) => setPrivacy(event.target.checked)} style={{ marginTop: 3 }} />
                <span>
                  <b>[필수]</b> 개인정보 수집·이용 동의
                  <br />
                  <span className="dim tiny">
                    이메일, 학습 이력, 캘린더 시간대를 수집합니다. 일정 제목과 참석자는 저장하지 않습니다.
                  </span>
                </span>
              </label>

              <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: '14px' }}>
                <input type="checkbox" checked={aiNotice} onChange={(event) => setAiNotice(event.target.checked)} style={{ marginTop: 3 }} />
                <span>
                  <b>[필수]</b> AI 생성 콘텐츠 고지 확인
                  <br />
                  <span className="dim tiny">
                    추천 목표와 학습 일정은 AI가 생성하며 부정확할 수 있습니다.
                  </span>
                </span>
              </label>

              <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: '14px' }}>
                <input type="checkbox" name="marketing" style={{ marginTop: 3 }} />
                <span><b className="muted">[선택]</b> 학습 알림 수신 (재조정 결과·마감 임박·학습 독촉)</span>
              </label>
            </fieldset>

            {formError && <p role="alert" className="hint hint-error">{formError}</p>}
            <button type="submit" className="btn btn-primary" disabled={!privacy || !aiNotice || pending}>
              {pending ? '저장 중...' : '가입 완료'}
            </button>
            <button type="button" className="btn btn-quiet" onClick={cancel} disabled={pending}>
              취소하고 로그아웃
            </button>
          </form>
        </>
      )}
    </main>
    </div>
  );
}
