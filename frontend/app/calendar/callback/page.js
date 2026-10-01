'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { saveBusy, takePending } from '@/lib/calendarBusy';

// FR-PLAN-01 구글 캘린더 동의에서 돌아오는 곳 — 바쁜 시간을 한 번 읽어 이 탭에 두고 계획 만들기로 돌아간다.
// 주소의 code·state 는 읽자마자 지운다. 내가 시작한 연결(state 일치)이 아니면 아무것도 하지 않는다.

const BACK = '/schedule#plan-builder';

// 개발 모드 StrictMode 가 effect 를 두 번 돌려도 code 를 한 번만 쓴다 (구글 code 는 한 번만 바꿀 수 있다)
let captured = null;

function capture() {
  if (captured) return captured;
  const params = new URLSearchParams(window.location.search);
  captured = { code: params.get('code'), state: params.get('state'), error: params.get('error') };
  captured.pending = takePending(captured.state);
  window.history.replaceState(null, '', window.location.pathname);
  return captured;
}

export default function CalendarCallbackPage() {
  const router = useRouter();
  const [message, setMessage] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      const got = capture();
      if (got.error) {
        if (alive) setMessage('구글 캘린더 연결을 취소했어요. 직접 고른 공부 시간으로 계획을 만들 수 있어요.');
        return;
      }
      if (!got.code || !got.pending) {
        if (alive) setMessage('연결 정보가 맞지 않아요. 계획 만들기 화면에서 다시 시도해 주세요.');
        return;
      }
      try {
        if (!got.result) {
          got.result = api.calendar.busy({ code: got.code, ...got.pending });
        }
        saveBusy(await got.result);
        if (alive) router.replace(BACK);
      } catch (err) {
        if (alive) setMessage(err.message || '구글 캘린더를 읽지 못했어요. 잠시 후 다시 시도해 주세요.');
      }
    })();
    return () => { alive = false; };
  }, [router]);

  return (
    <div className="focus">
      <main className="shell page stack" style={{ gap: 'var(--gap-3)', paddingTop: 'var(--gap-5)' }}>
        {!message ? (
          <p className="hint" role="status">구글 캘린더의 바쁜 시간을 읽고 있어요… 일정 제목은 읽지 않아요.</p>
        ) : (
          <>
            <h1 style={{ fontSize: 20 }}>캘린더를 가져오지 못했어요</h1>
            <p role="alert">{message}</p>
            <Link href={BACK} className="btn btn-primary">계획 만들기로 돌아가기</Link>
          </>
        )}
      </main>
    </div>
  );
}
