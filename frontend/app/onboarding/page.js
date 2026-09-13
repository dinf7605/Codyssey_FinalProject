'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AiBadge, AiNotice } from '@/components/AiNotice';
import { interestTags, goalSuggestions } from '@/lib/mock';

// 파이프라인 0 — 목표 탐색
// FR-GOAL-01 관심분야 입력 / FR-GOAL-02 가용 시간 / FR-GOAL-05 추천 카드 / FR-GOAL-07 확정
// 관심분야는 필수가 아니다. 건너뛰면 인기 목표 목록으로 진행한다 (FR-GOAL-11 콜드스타트).

const DAYS = ['월', '화', '수', '목', '금', '토', '일'];
const HOURS = ['오전', '오후', '저녁', '밤'];
const STEP_TITLES = ['관심 분야', '가능한 시간', '목표 고르기'];

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const [tags, setTags] = useState([]);
  const [slots, setSlots] = useState({});
  const [picked, setPicked] = useState(null);

  const slotCount = Object.values(slots).filter(Boolean).length;
  const weeklyHours = slotCount * 2;

  function toggleTag(tag) {
    setTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : prev.length >= 5 ? prev : [...prev, tag]
    );
  }

  function toggleSlot(key) {
    setSlots((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <main className="shell page" style={{ paddingBottom: 'var(--gap-6)' }}>
      <header className="stack" style={{ gap: 'var(--gap-3)', paddingTop: 'var(--gap-4)' }}>
        <div className="stepper">
          {STEP_TITLES.map((t, i) => (
            <span key={t} className={i <= step ? 'stepper-dot on' : 'stepper-dot'} />
          ))}
        </div>
        <div>
          <p className="dim tiny mono">STEP {step + 1} / 3</p>
          <h1 style={{ fontSize: 21, marginTop: 4 }}>
            {step === 0 && '어떤 분야에 관심이 있나요?'}
            {step === 1 && '언제 공부할 수 있나요?'}
            {step === 2 && '이 중에 해볼 만한 게 있나요?'}
          </h1>
        </div>
      </header>

      {step === 0 && (
        <section className="stack" style={{ gap: 'var(--gap-4)' }}>
          <p className="muted" style={{ fontSize: 14 }}>
            최대 5개까지 고를 수 있어요. 잘 모르겠으면 건너뛰어도 됩니다.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--gap-2)' }}>
            {interestTags.map((tag) => (
              <button
                key={tag}
                type="button"
                className="chip"
                aria-pressed={tags.includes(tag)}
                onClick={() => toggleTag(tag)}
              >
                {tag}
              </button>
            ))}
          </div>
          <div className="field">
            <label htmlFor="free">직접 입력</label>
            <input id="free" className="input" maxLength={100} placeholder="예) 데이터 분석 쪽으로 취업하고 싶어요" />
          </div>
        </section>
      )}

      {step === 1 && (
        <section className="stack" style={{ gap: 'var(--gap-4)' }}>
          <p className="muted" style={{ fontSize: 14 }}>
            공부할 수 있는 시간대를 눌러서 표시해 주세요. 주 3시간 이상을 권장합니다.
          </p>

          <div className="slots">
            <span />
            {DAYS.map((d) => (
              <span key={d} className="slot-head">{d}</span>
            ))}
            {HOURS.map((h) => (
              <SlotRow key={h} label={h} days={DAYS} slots={slots} onToggle={toggleSlot} />
            ))}
          </div>

          <div className="panel" style={{ padding: 'var(--gap-3) var(--gap-4)', display: 'flex', justifyContent: 'space-between' }}>
            <span className="muted tiny">선택한 주간 학습 시간</span>
            <span className="mono strong">{weeklyHours}시간</span>
          </div>

          {weeklyHours > 0 && weeklyHours < 3 && (
            <p className="hint hint-error">
              주 3시간 미만이면 대부분의 목표가 기한 안에 끝나지 않습니다. 그래도 진행할까요?
            </p>
          )}

          <p className="hint">구글 캘린더를 연동하면 빈 시간을 자동으로 채웁니다</p>
        </section>
      )}

      {step === 2 && (
        <section className="stack" style={{ gap: 'var(--gap-3)' }}>
          <p className="muted" style={{ fontSize: 14 }}>
            입력하신 주 {weeklyHours || 12}시간으로 <b>기한 안에 끝낼 수 있는 목표만</b> 남겼습니다.
          </p>

          <ul className="list">
            {goalSuggestions.map((g) => (
              <li key={g.id}>
                <button
                  type="button"
                  onClick={() => setPicked(g.id)}
                  className="panel"
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    padding: 'var(--gap-4)',
                    borderColor: picked === g.id ? 'var(--accent)' : 'var(--rule)',
                    background: picked === g.id ? 'var(--accent-soft)' : 'var(--surface)',
                  }}
                >
                  <div style={{ display: 'flex', gap: 'var(--gap-2)', marginBottom: 8 }}>
                    <AiBadge />
                    <span className="pill mono">{g.weeks}주 예상</span>
                    <span className="pill mono">주 {g.hoursPerWeek}시간</span>
                  </div>
                  <b style={{ fontSize: 16 }}>{g.title}</b>
                  <p style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 6, lineHeight: 1.6 }}>
                    {g.reason}
                  </p>
                </button>
              </li>
            ))}
          </ul>

          <AiNotice>
            추천 목표와 예상 기간은 AI가 생성하며 부정확할 수 있습니다. 시험일과 응시 자격은 직접 확인해 주세요.
          </AiNotice>
        </section>
      )}

      <div className="stack" style={{ gap: 'var(--gap-2)' }}>
        {step < 2 ? (
          <>
            <button type="button" className="btn btn-primary" onClick={() => setStep(step + 1)}>
              다음
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setStep(step + 1)}>
              건너뛰기
            </button>
          </>
        ) : (
          <>
            <Link
              href="/signup"
              className="btn btn-primary"
              aria-disabled={!picked}
              style={picked ? undefined : { pointerEvents: 'none', opacity: 0.45 }}
            >
              이 목표로 일정 만들기
            </Link>
            <p className="hint" style={{ textAlign: 'center' }}>
              일정 저장에는 가입이 필요합니다 · 방금 고른 값은 그대로 이어집니다
            </p>
          </>
        )}

        {step > 0 && (
          <button type="button" className="btn btn-ghost" onClick={() => setStep(step - 1)}>
            이전
          </button>
        )}
      </div>
    </main>
  );
}

// 요일 x 시간대 격자의 한 줄
function SlotRow({ label, days, slots, onToggle }) {
  return (
    <>
      <span className="slot-time">{label}</span>
      {days.map((d) => {
        const key = label + '-' + d;
        return (
          <button
            key={key}
            type="button"
            className="slot"
            aria-pressed={!!slots[key]}
            aria-label={d + '요일 ' + label}
            onClick={() => onToggle(key)}
          />
        );
      })}
    </>
  );
}
