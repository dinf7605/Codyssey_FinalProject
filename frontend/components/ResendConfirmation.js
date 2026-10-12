'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

// 가입 인증 메일 다시 보내기 — 가입 직후 안내 · 인증 전 로그인 안내에서 함께 쓴다 (backend POST /auth/resend-confirmation)
// 서버는 가입 여부와 상관없이 같은 문구를 돌려준다.
export default function ResendConfirmation({ email }) {
  const [state, setState] = useState({ status: 'idle', message: '' });

  async function resend() {
    setState({ status: 'sending', message: '' });
    try {
      const res = await api.auth.resendConfirmation({ email });
      setState({ status: 'sent', message: res.message });
    } catch (err) {
      setState({
        status: 'error',
        message: err.status === 429 || err.status === 503 ? err.message : '메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.',
      });
    }
  }

  return (
    <div className="stack" style={{ gap: 6 }}>
      <button type="button" className="btn btn-quiet btn-sm" onClick={resend} disabled={state.status === 'sending'}>
        {state.status === 'sending' ? '보내는 중…' : '인증 메일 다시 보내기'}
      </button>
      {state.message && <p className="hint" role="status" style={{ margin: 0 }}>{state.message}</p>}
    </div>
  );
}
