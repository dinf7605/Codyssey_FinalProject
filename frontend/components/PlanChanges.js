'use client';

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { api, getToken } from '@/lib/api';
import { PLAN_CHANGED, notifyPlanChanged } from '@/lib/usePlan';
import { whenLabel } from '@/lib/planView';
import { AiBadge, AiNotice } from './AiNotice';
import SectionTitle from './SectionTitle';

// FR-PLAN-07 최근 바뀐 일정 / FR-PLAN-06 되돌리기 1회 · 3일 연속이면 기한 조정 제안 (담당 C)
//
// 변경이 없으면 영역을 통째로 숨긴다 (기능명세). 최근 7일만 보관된다.

const TYPE_LABEL = { move: '이동', add: '추가', delete: '삭제', unplaced: '그대로 둠' };

const subscribeNothing = () => () => {};

export default function PlanChanges() {
  const hasToken = useSyncExternalStore(subscribeNothing, () => Boolean(getToken()), () => false);
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const load = useCallback(() => {
    if (!getToken()) return;
    api.plan.changes().then(setData, () => setData(null));
  }, []);

  useEffect(() => {
    load();
    window.addEventListener(PLAN_CHANGED, load);
    return () => window.removeEventListener(PLAN_CHANGED, load);
  }, [load]);

  if (!hasToken || !data || data.runs.length === 0) return null;

  const [latest, ...older] = data.runs;

  async function undo() {
    setBusy(true);
    setMessage('');
    try {
      const res = await api.plan.undoChanges(latest.id);
      setMessage(
        `${res.restored}개를 원래 자리로 되돌렸어요.` +
          (res.skipped ? ` ${res.skipped}개는 그사이 끝냈거나 직접 옮겨서 그대로 두었어요.` : ''),
      );
      notifyPlanChanged();
    } catch (err) {
      setMessage(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sec">
      <SectionTitle>최근 바뀐 일정</SectionTitle>

      {data.suggest_extension && (
        <div className="progress" role="note">
          <b>{data.streak_days}일 연속으로 블록이 뒤로 밀렸어요</b>
          <p className="muted tiny">
            지금 기한이 빠듯할 수 있어요. 아래 &apos;학습 계획 만들기&apos;에서 기한이나 공부 시간을 바꿔 다시 만들어 보세요.
          </p>
          <a className="btn btn-sm" href="#plan-builder">계획 다시 만들기</a>
        </div>
      )}

      <div className="stack" style={{ gap: 'var(--gap-2)' }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          {latest.ai_generated && <AiBadge />}
          <span className="tag">{whenLabel(latest.created_at)} 재조정</span>
          {latest.undone && <span className="pill">되돌림</span>}
        </div>
        <p style={{ fontSize: 14 }}>{latest.summary}</p>
        {latest.ai_generated && <AiNotice>요약 문장은 AI가 썼습니다. 바뀐 내용은 아래 목록이 정확합니다.</AiNotice>}
      </div>

      <ul className="rows">
        {latest.changes.map((c, i) => (
          <li className="row" key={`${c.title}-${i}`}>
            <div className="row-main">
              <b>{c.title}</b>
              <span>
                {c.after_start ? `${whenLabel(c.before_start)} → ${whenLabel(c.after_start)}` : whenLabel(c.before_start)}
              </span>
              <span className="dim tiny">{c.reason}</span>
            </div>
            <span className={c.type === 'unplaced' ? 'pill pill-late' : 'pill'}>{TYPE_LABEL[c.type] || c.type}</span>
          </li>
        ))}
      </ul>

      {latest.can_undo && (
        <button type="button" className="btn btn-sm" disabled={busy} onClick={undo}>
          {busy ? '되돌리는 중…' : '이번 재조정 되돌리기 (1회)'}
        </button>
      )}
      {message && <p className="hint" role="status">{message}</p>}
      <p className="hint">매일 새벽 3시에 지난 미완료 블록을 남은 기간에 다시 놓아요. 직접 옮긴 블록은 건드리지 않아요.</p>

      {older.length > 0 && (
        <>
          <button type="button" className="btn btn-quiet btn-sm" onClick={() => setOpen((v) => !v)}>
            {open ? '지난 내역 접기' : `지난 7일 내역 ${older.length}건 보기`}
          </button>
          {open && (
            <ul className="rows">
              {older.map((r) => (
                <li className="row" key={r.id}>
                  <div className="row-main">
                    <b>{whenLabel(r.created_at)}</b>
                    <span>{r.summary}</span>
                  </div>
                  {r.undone && <span className="pill">되돌림</span>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
