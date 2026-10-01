'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import EmptyState from '@/components/EmptyState';
import { api, getToken } from '@/lib/api';
import { notifyPlanChanged } from '@/lib/usePlan';
import { alreadyAsked, browserAlertState, requestBrowserAlerts } from '@/lib/browserAlerts';

// FR-ALARM-01~04 앱 안 알림 · FR-ALARM-03 알림에서 바로 처리 (지금 시작 / 미루기 2번까지 / 오늘 쉬기)
// 알림은 서버의 알림 워커가 만든다 (backend/services/alarms.py). 이 화면은 보여 주고 처리만 한다.
// 알림 켜기·시간·방해금지·강도는 내정보 → 알림 설정에서 바꾼다.

const TYPE_LABEL = {
  '10min_before': '시작 전',
  after_block: '미완료',
  daily_nightly: '하루 마감',
  weekly_summary: '주간 요약',
  replan_result: '재조정 결과',
  contest_deadline: '공모전 마감',
  rest_today: '오늘 쉬기',
};

function when(iso) {
  return new Date(iso).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul', hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function NotificationsPage() {
  const [state, setState] = useState({ status: 'loading', rows: [] });
  const [busy, setBusy] = useState(null);       // 처리 중인 알림 id
  const [notice, setNotice] = useState({});     // 알림 id → 처리 결과 문구
  // FR-ALARM-01 — 브라우저 알림 권한은 처음 한 번만 묻는다. 거부했으면 다시 묻지 않는다
  const [askBrowser, setAskBrowser] = useState(() => browserAlertState() === 'default' && !alreadyAsked());

  useEffect(() => {
    let alive = true;
    if (!getToken()) {
      Promise.resolve().then(() => alive && setState({ status: 'login', rows: [] }));
      return () => { alive = false; };
    }
    api.notifications.list().then(
      (rows) => alive && setState({ status: 'ready', rows }),
      (err) => alive && setState({ status: err.status === 401 ? 'login' : 'error', rows: [] }),
    );
    return () => { alive = false; };
  }, []);

  function markRead(id) {
    setState((old) => ({ ...old, rows: old.rows.map((r) => (r.id === id ? { ...r, is_read: true } : r)) }));
    api.notifications.read(id).catch(() => {});  // 읽음 표시 실패는 다음에 다시 열면 그대로 보일 뿐이다
  }

  async function readAll() {
    setState((old) => ({ ...old, rows: old.rows.map((r) => ({ ...r, is_read: true })) }));
    try { await api.notifications.readAll(); } catch { /* 다음 조회 때 다시 보인다 */ }
  }

  async function postpone(row) {
    setBusy(row.id);
    try {
      const res = await api.plan.postponeBlock(row.block_id);
      const start = res.block?.start ? when(res.block.start) : '';
      setNotice((old) => ({ ...old, [row.id]: { ok: true, text: `${start}로 미뤘어요. 뒤 단원도 순서대로 옮겼어요.` } }));
      markRead(row.id);
      notifyPlanChanged();
    } catch (err) {
      setNotice((old) => ({ ...old, [row.id]: { ok: false, text: err.message || '미루지 못했어요. 일정에서 직접 옮겨 주세요.' } }));
    } finally {
      setBusy(null);
    }
  }

  async function restToday(row) {
    setBusy(row.id);
    try {
      const res = await api.notifications.restToday();
      setNotice((old) => ({ ...old, [row.id]: { ok: true, text: res.message } }));
      markRead(row.id);
    } catch (err) {
      setNotice((old) => ({ ...old, [row.id]: { ok: false, text: err.message || '처리하지 못했어요. 잠시 후 다시 시도해 주세요.' } }));
    } finally {
      setBusy(null);
    }
  }

  async function allowBrowser() {
    await requestBrowserAlerts();
    setAskBrowser(false);
  }

  if (state.status === 'loading') return <p className="hint" role="status">알림을 불러오는 중…</p>;
  if (state.status === 'login') {
    return <EmptyState title="로그인하면 학습 알림을 볼 수 있어요"
      action={<Link className="btn btn-sm" href="/login?next=/notifications">로그인</Link>} />;
  }
  if (state.status === 'error') return <p className="hint hint-error" role="alert">알림을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.</p>;

  const unread = state.rows.filter((r) => !r.is_read).length;

  return (
    <>
      <header className="stack" style={{ gap: 6 }}>
        <h1 style={{ fontSize: 20 }}>알림</h1>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <p className="muted tiny" style={{ margin: 0 }}>최근 50건 · 안 읽음 {unread}건</p>
          {unread > 0 && <button type="button" className="btn btn-sm" onClick={readAll}>모두 읽음</button>}
          <Link href="/mypage#notification-settings" className="tiny accent-text">알림 설정</Link>
        </div>
        {askBrowser && (
          <div className="panel" style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', padding: 'var(--gap-3)' }}>
            <span className="tiny">사이트를 열어 둔 동안 브라우저 알림으로도 받을까요?</span>
            <button type="button" className="btn btn-sm btn-primary" onClick={allowBrowser}>브라우저 알림 받기</button>
            <button type="button" className="btn btn-sm btn-quiet" onClick={() => setAskBrowser(false)}>나중에</button>
          </div>
        )}
      </header>

      {state.rows.length === 0 ? (
        <EmptyState title="아직 알림이 없어요" description="학습 블록 시작 전, 끝내지 못한 블록, 주간 요약, 관심 공모전 마감을 여기서 알려 드려요." />
      ) : (
        <ul className="stack" style={{ gap: 0, listStyle: 'none', padding: 0, margin: 0 }} aria-label="알림 목록">
          {state.rows.map((row) => {
            const result = notice[row.id];
            return (
              <li key={row.id} className={row.is_read ? 'noti-item' : 'noti-item noti-unread'}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
                  <span className={row.is_read ? 'tag' : 'tag tag-accent'}>{TYPE_LABEL[row.type] || '알림'}</span>
                  <span className="micro dim mono">{when(row.sent_at)}</span>
                  {!row.is_read && <span className="micro accent-text">안 읽음</span>}
                </div>
                <p className="noti-msg" style={{ margin: 0 }}>{row.message}</p>
                {row.actions?.length > 0 && !result?.ok && (
                  <div className="noti-actions">
                    <Link className="btn btn-sm btn-primary" href={`/study?block=${encodeURIComponent(row.block_id)}`}
                      onClick={() => markRead(row.id)}>지금 시작</Link>
                    {row.actions.includes('postpone') && (
                      <button type="button" className="btn btn-sm" disabled={busy === row.id} onClick={() => postpone(row)}>
                        {busy === row.id ? '처리 중…' : '다음 빈 시간으로 미루기'}
                      </button>
                    )}
                    {row.actions.includes('rest') && (
                      <button type="button" className="btn btn-sm btn-quiet" disabled={busy === row.id} onClick={() => restToday(row)}>
                        오늘은 쉬기
                      </button>
                    )}
                  </div>
                )}
                {result && <p className={result.ok ? 'hint' : 'hint hint-error'} role="status" style={{ margin: 0 }}>{result.text}</p>}
                {!result && row.handled && <p className="hint" style={{ margin: 0 }}>{row.handled}</p>}
                {!row.is_read && !row.actions?.length && (
                  <button type="button" className="btn btn-sm btn-quiet" onClick={() => markRead(row.id)} style={{ alignSelf: 'flex-start' }}>
                    읽음으로 표시
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
