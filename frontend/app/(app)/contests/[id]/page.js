'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { AiBadge, AiNotice } from '@/components/AiNotice';
import { contests } from '@/lib/mock';
import { dday } from '@/lib/ui';

// FR-CONT-10 준비 기간 산정 — 비회원도 로그인 없이 계산할 수 있다.
// FR-CONT-11 계산 결과를 일정으로 만들려면 가입으로 유도한다.
// 계산은 LLM을 쓰지 않는 결정론적 나눗셈이다 (기획서 4-2절).

const STANDARD_HOURS = 40;

export default function ContestDetailPage() {
  const params = useParams();
  const contest = contests.find((c) => c.id === params.id) || contests[0];
  const [hours, setHours] = useState(8);

  const weeksNeeded = Math.ceil(STANDARD_HOURS / Math.max(hours, 1));
  const weeksLeft = Math.floor(contest.dDay / 7);
  const verdict = weeksLeft >= weeksNeeded * 1.3 ? 'ok' : weeksLeft >= weeksNeeded ? 'warn' : 'late';
  const verdictText = { ok: '가능', warn: '빠듯함', late: '이번 회차는 어렵습니다' }[verdict];

  return (
    <>
      <header className="stack" style={{ gap: 'var(--gap-2)' }}>
        <div style={{ display: 'flex', gap: 'var(--gap-2)', flexWrap: 'wrap' }}>
          <span className="pill mono">{dday(contest.dDay)}</span>
          <span className="pill">{contest.field}</span>
        </div>
        <h1 style={{ fontSize: 19, lineHeight: 1.4 }}>{contest.title}</h1>
        <p className="muted tiny">{contest.host} · 마감 {contest.deadline}</p>
      </header>

      <section className="panel" style={{ padding: 'var(--gap-4)' }}>
        <div style={{ display: 'flex', gap: 'var(--gap-2)', alignItems: 'center', marginBottom: 'var(--gap-2)' }}>
          <h2 style={{ fontSize: 15 }}>추천 이유</h2>
          <AiBadge />
        </div>
        <p style={{ fontSize: 14, color: 'var(--ink-2)', lineHeight: 1.65 }}>{contest.reason}</p>
        <div style={{ marginTop: 'var(--gap-3)' }}>
          <AiNotice>
            지원 자격 충족 여부는 단정할 수 없습니다. 반드시 공고 원문을 확인해 주세요.
          </AiNotice>
        </div>
      </section>

      <section className="panel" style={{ padding: 'var(--gap-4)' }}>
        <h2 style={{ fontSize: 15 }}>얼마나 준비해야 할까요</h2>
        <p className="muted tiny" style={{ marginTop: 4 }}>
          주당 투입 가능 시간을 넣으면 최소 준비 기간을 계산합니다
        </p>

        <div className="field" style={{ marginTop: 'var(--gap-4)' }}>
          <label htmlFor="hours">주당 투입 가능 시간: {hours}시간</label>
          <input
            id="hours"
            type="range"
            min={1}
            max={30}
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            style={{ width: '100%' }}
          />
        </div>

        <div
          style={{
            marginTop: 'var(--gap-3)',
            paddingTop: 'var(--gap-3)',
            borderTop: '1px solid var(--rule)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 'var(--gap-3)',
          }}
        >
          <div className="stack" style={{ gap: 2 }}>
            <span className="dim tiny">최소 필요 기간</span>
            <span className="mono" style={{ fontSize: 18, fontWeight: 600 }}>{weeksNeeded}주</span>
          </div>
          <span className={'badge badge-' + verdict}>{verdictText}</span>
        </div>

        <p className="hint" style={{ marginTop: 'var(--gap-2)' }}>
          표준 준비시간이 없는 분야는 유사 분야 중앙값으로 계산한 추정치입니다
        </p>

        <button className="btn btn-primary" style={{ marginTop: 'var(--gap-4)' }}>
          이 준비 기간으로 일정 만들기
        </button>
        <p className="hint" style={{ marginTop: 6, textAlign: 'center' }}>
          일정 저장에는 가입이 필요합니다 · 계산한 값은 그대로 이어집니다
        </p>
      </section>
    </>
  );
}
