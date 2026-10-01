'use client';

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { api, getToken } from '@/lib/api';
import { PLAN_CHANGED } from '@/lib/usePlan';
import { whenLabel } from '@/lib/planView';
import SectionTitle from './SectionTitle';

// FR-STUDY-05 학습 메모 — 블록마다 남긴 짧은 회고를 목표별로 모아본다 (담당 C)
//
// 끝낸 목표의 메모도 보여 준다. 계획 블록 없이 적은 메모는 '목표 없이 적은 메모'로 묶는다.
// 메모가 하나도 없으면 영역을 숨긴다 — 선택 입력이라 비어 있는 것이 보통이다.

const PREVIEW = 5; // 목표마다 처음에 보여 줄 메모 수
const FREE = 'free';

const subscribeNothing = () => () => {};
const keyOf = (g) => g.plan_id || FREE;
const nameOf = (g) => g.goal_title || '목표 없이 적은 메모';

export default function StudyNotes() {
  const hasToken = useSyncExternalStore(subscribeNothing, () => Boolean(getToken()), () => false);
  const [groups, setGroups] = useState(null);
  const [focus, setFocus] = useState('all');
  const [expanded, setExpanded] = useState({});

  const latest = useRef(0);

  // 늦게 도착한 이전 응답이 새 결과를 덮지 않게 마지막 요청만 반영한다.
  // 불러오기에 실패하면 보이던 메모를 그대로 둔다 (잠깐 끊겼다고 목록이 사라지면 안 된다)
  const load = useCallback(() => {
    if (!getToken()) return;
    const seq = ++latest.current;
    api.study.notes().then(
      (res) => seq === latest.current && setGroups(res.groups),
      () => {},
    );
  }, []);

  useEffect(() => {
    load();
    window.addEventListener(PLAN_CHANGED, load); // 기록을 저장하면 PLAN_CHANGED 가 온다
    return () => window.removeEventListener(PLAN_CHANGED, load);
  }, [load]);

  if (!hasToken || !groups?.length) return null;

  const focusKey = groups.some((g) => keyOf(g) === focus) ? focus : 'all';
  const shown = focusKey === 'all' ? groups : groups.filter((g) => keyOf(g) === focusKey);

  return (
    <section className="sec" aria-label="학습 메모 모아보기">
      <SectionTitle>메모 모아보기</SectionTitle>

      {groups.length > 1 && (
        <div className="chips" role="group" aria-label="목표 골라 보기">
          <button type="button" className="chip" aria-pressed={focusKey === 'all'} onClick={() => setFocus('all')}>전체</button>
          {groups.map((g) => (
            <button key={keyOf(g)} type="button" className="chip" aria-pressed={focusKey === keyOf(g)}
              onClick={() => setFocus(keyOf(g))}>
              {nameOf(g)}
            </button>
          ))}
        </div>
      )}

      {shown.map((g) => {
        const open = expanded[keyOf(g)];
        const notes = open ? g.notes : g.notes.slice(0, PREVIEW);
        return (
          <div className="stack" style={{ gap: 'var(--gap-2)' }} key={keyOf(g)}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <b style={{ fontSize: '14px' }}>{nameOf(g)}</b>
              <span className="tag">메모 {g.notes.length}개</span>
              {g.plan_id && !g.active && <span className="pill">끝낸 목표</span>}
            </div>
            <ul className="rows">
              {notes.map((n) => (
                <li className="row" key={n.id}>
                  <div className="row-main">
                    <b style={{ fontWeight: 400, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{n.note}</b>
                    <span className="dim tiny">
                      {whenLabel(n.started_at)} · {n.minutes}분{n.block_title ? ` · ${n.block_title}` : ''}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            {g.notes.length > PREVIEW && (
              <button type="button" className="btn btn-quiet btn-sm"
                onClick={() => setExpanded((e) => ({ ...e, [keyOf(g)]: !open }))}>
                {open ? '접기' : `${g.notes.length - PREVIEW}개 더 보기`}
              </button>
            )}
          </div>
        );
      })}
    </section>
  );
}
