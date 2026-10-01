'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, getToken } from '@/lib/api';
import { signOut } from '@/components/AccountSettings';
import { CONTENT } from '@/components/SignupConsentFields';

// FR-JOIN-03 — AI 이용 고지 문구가 바뀌면(backend AI_NOTICE_VERSION) 다음 로그인 때 다시 동의를 받는다.
// 로그인한 화면 공통 레이아웃에서 한 번 확인한다. 동의하지 않으면 로그아웃할 수 있다 — AI 기능 대부분이 이 고지를 전제로 한다.

const NOTICE = CONTENT.ai;

export default function ReconsentGate() {
  const router = useRouter();
  const [needed, setNeeded] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const dialogRef = useRef(null);

  useEffect(() => {
    if (!getToken()) return undefined;
    let alive = true;
    api.auth.consent().then(
      (res) => alive && setNeeded(Boolean(res.needs_ai_notice)),
      () => {},  // 확인하지 못하면 묻지 않는다 — 다음 접속 때 다시 본다
    );
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (needed && dialog && !dialog.open) dialog.showModal();
  }, [needed]);

  async function agree() {
    setPending(true);
    setError('');
    try {
      await api.auth.agreeAiNotice();
      dialogRef.current?.close();
      setNeeded(false);
    } catch (err) {
      setError(err.message || '저장하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setPending(false);
    }
  }

  function logout() {
    dialogRef.current?.close();
    setNeeded(false);
    signOut();
    router.push('/login');
  }

  if (!needed) return null;

  return (
    <dialog ref={dialogRef} className="panel" aria-labelledby="reconsent-title"
      onCancel={(event) => event.preventDefault()}
      style={{ maxWidth: 560, width: 'calc(100% - 32px)', padding: 'var(--gap-4)', border: '1px solid var(--rule)' }}>
      <div className="stack" style={{ gap: 10 }}>
        <p className="tiny accent-text" style={{ margin: 0 }}>안내가 바뀌었어요</p>
        <h2 id="reconsent-title" style={{ fontSize: 17, margin: 0 }}>{NOTICE.title}</h2>
        <p className="tiny" style={{ margin: 0 }}>{NOTICE.introduction}</p>
        <div className="stack" style={{ gap: 8, maxHeight: '45vh', overflowY: 'auto' }}>
          {NOTICE.sections.map((section) => (
            <section key={section.title} className="stack" style={{ gap: 4 }}>
              <h3 className="tiny strong" style={{ margin: 0 }}>{section.title}</h3>
              {section.paragraphs?.map((p) => <p key={p} className="tiny muted" style={{ margin: 0 }}>{p}</p>)}
              {section.items && (
                <ul className="tiny muted" style={{ margin: 0, paddingLeft: 18 }}>
                  {section.items.map((item) => <li key={item}>{item}</li>)}
                </ul>
              )}
            </section>
          ))}
        </div>
        <p className="tiny" style={{ margin: 0 }}>{NOTICE.acknowledgement}</p>
        {error && <p className="hint hint-error" role="alert" style={{ margin: 0 }}>{error}</p>}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-sm btn-primary" disabled={pending} onClick={agree}>
            {pending ? '저장 중…' : NOTICE.action}
          </button>
          <button type="button" className="btn btn-sm btn-quiet" disabled={pending} onClick={logout}>동의하지 않고 로그아웃</button>
        </div>
      </div>
    </dialog>
  );
}
