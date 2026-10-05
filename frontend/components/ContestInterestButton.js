'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, getToken } from '@/lib/api';
import { ddayOf, kstToday } from '@/lib/planView';
import { notifyPlanChanged } from '@/lib/usePlan';

// FR-CONT-07 관심 공모전 등록 — 마감 D-7 · D-3 준비 블록을 진행 중인 목표에 넣는다 (backend/services/contest_interest.py)
// 일정이 바뀌므로 넣기 전에 놓일 자리를 먼저 보여 주고 확인을 받는다. 자리가 없는 날은 그날 일정과 이유를 보여 주고,
// 자리를 찾은 블록만 넣어(없으면 블록 없이) 관심 등록한다.
// 관심을 해제하면 아직 안 한 준비 블록도 함께 지운다.
// 마감이 3일 안이면 준비 블록을 놓을 날이 없으므로 버튼 대신 이유를 보여 준다 (서버도 같은 기준으로 거절한다).

const LAST_PREP_DAYS = 3; // backend services/contest_interest.py PREP_DAYS 의 가장 가까운 날

function when(iso) {
  return new Date(`${iso}+09:00`).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul', hour12: false, month: 'numeric', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit',
  });
}

export default function ContestInterestButton({ contestId, deadline }) {
  const tooLate = !deadline || ddayOf(deadline, kstToday()) < LAST_PREP_DAYS;
  const [token] = useState(() => getToken());
  const [state, setState] = useState({ status: token ? 'loading' : 'anon', interest: null });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState({ ok: true, text: '' });

  useEffect(() => {
    if (!token) return undefined;
    let alive = true;
    api.contestInterests.list().then(
      (res) => alive && setState({ status: 'ready', interest: res.interests.find((i) => i.contest_id === contestId) || null }),
      () => alive && setState({ status: 'ready', interest: null }),
    );
    return () => { alive = false; };
  }, [token, contestId]);

  async function look() {
    setBusy(true);
    setMessage({ ok: true, text: '' });
    try {
      setPreview(await api.contestInterests.preview(contestId));
    } catch (err) {
      setMessage({ ok: false, text: err.message || '준비 블록 자리를 계산하지 못했어요.' });
    } finally {
      setBusy(false);
    }
  }

  async function confirmAdd() {
    setBusy(true);
    try {
      const res = await api.contestInterests.add(contestId);
      setState({ status: 'ready', interest: { contest_id: contestId, prep_blocks: res.blocks.length } });
      setPreview(null);
      setMessage({
        ok: true,
        text: res.blocks.length
          ? `관심 등록했어요. '${res.goal_title}' 일정에 준비 블록 ${res.blocks.length}개를 넣었어요.`
          : '관심 등록했어요. 준비 블록은 넣지 않았어요.',
      });
      notifyPlanChanged();
    } catch (err) {
      setMessage({ ok: false, text: err.message || '등록하지 못했어요.' });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm('관심을 해제할까요? 아직 하지 않은 준비 블록도 일정에서 지워져요.')) return;
    setBusy(true);
    try {
      const res = await api.contestInterests.remove(contestId);
      setState({ status: 'ready', interest: null });
      setMessage({ ok: true, text: `관심을 해제하고 준비 블록 ${res.removed_blocks}개를 지웠어요.` });
      notifyPlanChanged();
    } catch (err) {
      setMessage({ ok: false, text: err.message || '해제하지 못했어요.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel stack" style={{ padding: 'var(--gap-4)', gap: 8 }} aria-labelledby="interest-title">
      <h2 id="interest-title" style={{ fontSize: '14px' }}>관심 공모전</h2>
      {state.status === 'anon' && (
        <p className="hint" style={{ margin: 0 }}>
          관심 등록하면 마감 7일 전·3일 전에 준비 블록을 일정에 넣어 드려요.{' '}
          <Link href={`/login?next=/contests/${encodeURIComponent(contestId)}`}>로그인하기</Link>
        </p>
      )}
      {state.status === 'ready' && state.interest && (
        <>
          <p className="tiny" style={{ margin: 0 }}>
            관심 등록한 공모전이에요 · 준비 블록 {state.interest.prep_blocks}개. 마감 24시간 전 알림은 알림 설정의 &lsquo;관심 공모전 마감 임박&rsquo;을 켜면 받아요.
          </p>
          <button type="button" className="btn btn-sm btn-quiet" disabled={busy} onClick={remove} style={{ alignSelf: 'flex-start' }}>
            관심 해제
          </button>
        </>
      )}
      {state.status === 'ready' && !state.interest && !preview && tooLate && (
        <p className="muted tiny" style={{ margin: 0 }}>
          마감이 3일 안이라 준비 블록을 넣을 날이 없어요. 관심 등록은 마감 3일 전까지 할 수 있어요.
        </p>
      )}
      {state.status === 'ready' && !state.interest && !preview && !tooLate && (
        <>
          <p className="muted tiny" style={{ margin: 0 }}>마감 7일 전·3일 전에 1시간짜리 준비 블록을 진행 중인 목표 일정에 넣어요. 넣기 전에 자리를 먼저 보여 드려요.</p>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={look} style={{ alignSelf: 'flex-start' }}>
            {busy ? '자리 찾는 중…' : '관심 등록하기'}
          </button>
        </>
      )}
      {preview && (
        <div className="stack" style={{ gap: 6 }}>
          <p className="tiny" style={{ margin: 0 }}>&lsquo;{preview.goal_title}&rsquo; 일정에 이렇게 넣어요.</p>
          <ul className="tiny" style={{ margin: 0, paddingLeft: 18 }}>
            {preview.blocks.map((b) => (
              <li key={b.unit_key}>
                {when(b.start)} · 1시간 · {b.title}
                {b.shifted_days > 0 && <span className="muted"> (그날 자리가 없어 {b.shifted_days}일 앞당김)</span>}
              </li>
            ))}
          </ul>
          {preview.conflicts.length > 0 && (
            <div className="stack" style={{ gap: 4 }} role="alert">
              {preview.conflicts.map((c) => (
                <div key={c.day} className="tiny">
                  <b style={{ color: 'var(--late)' }}>{c.label}에는 넣을 자리가 없어요.</b> {c.reason}
                  {c.blocks.length > 0 && (
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {c.blocks.map((b) => <li key={b.start}>{when(b.start)} {b.title}</li>)}
                    </ul>
                  )}
                </div>
              ))}
              <p className="hint" style={{ margin: 0 }}>
                {preview.blocks.length > 0
                  ? '자리를 찾은 블록만 넣고 관심 등록할 수 있어요. 나머지도 넣으려면 그날 블록을 옮기거나 공부 가능 시간을 늘린 뒤 다시 시도해 주세요.'
                  : '준비 블록 없이 관심 등록만 할 수 있어요 — 마감 임박 알림은 받을 수 있어요.'}
              </p>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {/* 예전엔 하나라도 자리가 없으면 버튼이 꺼져 관심 등록 자체를 못 했다 (10-05 사전 점검 3번) */}
            <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={confirmAdd}>
              {busy
                ? '넣는 중…'
                : preview.conflicts.length === 0
                ? '이대로 넣기'
                : preview.blocks.length > 0
                ? `${preview.blocks.length}개만 넣고 등록`
                : '블록 없이 관심만 등록'}
            </button>
            <button type="button" className="btn btn-sm btn-quiet" disabled={busy} onClick={() => setPreview(null)}>취소</button>
          </div>
        </div>
      )}
      {message.text && <p className={message.ok ? 'hint' : 'hint hint-error'} role="status" style={{ margin: 0 }}>{message.text}</p>}
    </section>
  );
}
