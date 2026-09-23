'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AiBadge, AiNotice } from '@/components/AiNotice';
import EmptyState from '@/components/EmptyState';
import { interestTags as fallbackTags } from '@/lib/mock';
import { api } from '@/lib/api';
import { getAnonSessionId, saveExploration } from '@/lib/goalSession';

// 파이프라인 0 — 목표 탐색 (담당 B, FR-GOAL-01~13)
//
// 화면은 선형 스텝이 아니라 아래처럼 갈라진다.
//
//   interest ──(입력 있음)──────────────┐
//      └─(입력 없음)→ suggested ────────┼─→ time → matching → recommend ─┬─→ confirm
//                                                                          │
//                     recommend ──"직접 입력"──→ manual → manual-warn ────┘
//
// 한도 초과(FR-GOAL-12)에 걸리면 어느 단계에서든 limited 로 빠진다.
// 목표 확정(FR-GOAL-07) 뒤 가입 쪽은 아직 제출 동작이 없어(README 참고),
// 여기서는 탐색 결과를 로컬에 저장해 두고(FR-GOAL-13) /signup 으로 넘긴다.

const DAYS = ['월', '화', '수', '목', '금', '토', '일'];
const HOURS = ['오전', '오후', '저녁', '밤'];
const STEP_OF_VIEW = {
  interest: 1,
  suggested: 1,
  time: 2,
  matching: 3,
  recommend: 3,
  manual: 3,
  'manual-warn': 3,
  confirm: 4,
  limited: 3,
};
// FR-GOAL-01 자유입력(freeText)을 검색용 태그로 바꾼다.
// 지금까지 freeText는 "입력이 있는지" 판단(hasInput)에만 쓰이고 정작 /goal/recommend
// 호출에는 tags(칩으로 고른 값)만 실려 갔다 — 태그를 하나도 안 고르고 자유입력만
// 채운 경우 tags=[]로 검색되어 항상 fallback_popular로 빠지는 버그였다("토익"이라고
// 입력해도 전혀 상관없는 인기 목록이 나오던 문제). 카탈로그 매칭이 태그 겹침 기반이라
// (goal_catalog.search_catalog) 문장을 통째로 넘기면 못 맞히므로, 공백/구두점으로
// 쪼갠 단어 단위로 넘겨 "토익"·"SQLD"처럼 카탈로그 태그와 그대로 겹치는 단어는
// 잡히게 한다.
function freeTextTokens(text) {
  if (!text) return [];
  return text
    .split(/[\s,·/]+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2);
}

const FEEDBACK_REASONS = [
  { id: 'field_mismatch', label: '분야 안 맞음' },
  { id: 'too_long', label: '기간 부담' },
  { id: 'already_have', label: '이미 취득' },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [view, setView] = useState('interest');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [availableTags, setAvailableTags] = useState(fallbackTags);
  const [tags, setTags] = useState([]);
  const [freeText, setFreeText] = useState('');

  const [suggestedTags, setSuggestedTags] = useState([]);
  const [popularGoals, setPopularGoals] = useState([]);

  const [slots, setSlots] = useState({});
  const slotCount = Object.values(slots).filter(Boolean).length;
  const weeklyHours = slotCount * 2;

  const [candidates, setCandidates] = useState([]);
  const [queryUsed, setQueryUsed] = useState('tags');
  const [allExceeded, setAllExceeded] = useState(false);
  // 기한을 못 맞춰 candidates에서 빠진 후보들 (표준시간·최소기간·마감일 포함).
  // /goal/feasibility, /goal/recommend 응답의 excluded 필드를 그대로 담는다 — 태그 검색·
  // 인기목록 대체·인기 목표 직접선택 세 경로 전부 여기서 "왜 기한을 맞추기 어려운지"를
  // 보여줄 수 있다 (예전엔 인기 목표 직접선택 경로만 프론트에서 따로 계산했었다).
  const [excludedCandidates, setExcludedCandidates] = useState([]);
  const [feedbackDone, setFeedbackDone] = useState({}); // goal_id -> true (제출 후 카드 숨김)
  const [reasonPromptFor, setReasonPromptFor] = useState(null);

  const [manualGoal, setManualGoal] = useState({ title: '', dueDate: '', weeklyHours: '' });
  const [manualWarning, setManualWarning] = useState(null);

  const [picked, setPicked] = useState(null); // 확정할 목표 (추천 카드 또는 직접 입력)
  const [limitMessage, setLimitMessage] = useState('');
  const [limitOrigin, setLimitOrigin] = useState('interest'); // 한도에 걸리기 직전 화면 — "이전" 복귀용
  const [provisionalPick, setProvisionalPick] = useState(null); // 인기 목표 목록에서 직접 고른 후보
  const [pickOrigin, setPickOrigin] = useState('interest'); // 그 후보를 고르기 직전 화면 — "이전" 복귀용

  useEffect(() => {
    let cancelled = false;
    api.goal
      .tags()
      .then((res) => {
        if (!cancelled && res?.tags?.length) setAvailableTags(res.tags);
      })
      .catch(() => {
        /* API가 아직 없으면 mock.js 목록으로 대신한다 */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 다른 페이지로 나갔다가 브라우저 뒤로/앞으로가기로 돌아오면, 브라우저가 이 페이지를
  // 통째로 메모리(bfcache)에서 복원해서 리액트 state까지 그대로 살아있을 수 있다.
  // 온보딩 흐름 안에서 "다음 → 이전"으로 되돌아온 건 컴포넌트가 계속 살아있는
  // 정상적인 경우라 값을 유지해야 하지만, bfcache 복원은 "다른 루트를 거쳐 돌아온"
  // 경우이므로 이때는 가용시간 선택을 리셋한다.
  useEffect(() => {
    function handlePageShow(e) {
      if (e.persisted) {
        setSlots({});
      }
    }
    window.addEventListener('pageshow', handlePageShow);
    return () => window.removeEventListener('pageshow', handlePageShow);
  }, []);

  function toggleTag(tag) {
    setTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : prev.length >= 5 ? prev : [...prev, tag]
    );
  }

  function toggleSlot(key) {
    setSlots((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  // runLimited가 방금 호출을 429(한도 초과)로 처리했는지를 호출부에 알려주기 위한 플래그.
  // setView는 비동기 갱신이라 "limited로 바꿨다가 곧바로 다른 값으로 덮어쓰는" 실수를
  // 막으려면, 호출부가 상태값 대신 이 ref를 보고 분기해야 한다.
  const lastLimitedRef = useRef(false);

  async function runLimited(fn, origin) {
    lastLimitedRef.current = false;
    setBusy(true);
    setError('');
    try {
      return await fn();
    } catch (err) {
      if (err.status === 429) {
        lastLimitedRef.current = true;
        setLimitMessage(err.message);
        setLimitOrigin(origin);
        setView('limited');
      } else {
        setError(err.message || '요청이 실패했습니다.');
      }
      return null;
    } finally {
      setBusy(false);
    }
  }

  // ── STEP 1: 관심분야 입력 (FR-GOAL-01) ──────────────────────
  async function handleInterestNext(forceSkip = false) {
    // 태그로 정상 진행하는 경로다. 전에 인기 목표를 하나 찍어뒀다가(provisionalPick)
    // 이전으로 돌아와 이 경로로 다시 들어오면, 남아있는 provisionalPick이 다음
    // "가용시간 다음" 클릭 때 태그 대신 그 후보 하나만 계산하게 가로채 버리므로 지운다.
    // pickOrigin도 함께 초기화해야, 이 경로로 새로 들어온 뒤 "이전"을 눌렀을 때
    // 예전에 인기 목표를 골랐던 화면(예: suggested)이 아니라 이 화면(interest)으로 돌아온다.
    setProvisionalPick(null);
    setPickOrigin('interest');
    const hasInput = !forceSkip && (tags.length > 0 || freeText.trim().length > 0);
    if (hasInput) {
      setView('time');
      return;
    }
    if (forceSkip) {
      setTags([]);
      setFreeText('');
    }
    // 입력이 0건 → FR-GOAL-11 유사분야 추천 경로
    const res = await runLimited(
      () => api.goal.suggest({ sessionId: getAnonSessionId(), recentGoalTags: [], recentViewedFields: [] }),
      'interest'
    );
    if (!res) return;
    setSuggestedTags(res.tags || []);
    setPopularGoals(res.popular || []);
    setView('suggested');
  }

  // ── STEP 1-대체: 유사분야 추천 / 인기 목록 (FR-GOAL-11) ────────
  function toggleSuggestedTag(tag) {
    setTags((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]));
  }

  // 인기 목표 목록(FR-GOAL-11 콜드스타트 / FR-GOAL-12 한도초과 화면 공용)에서
  // 카드를 바로 골랐을 때. 여기서 고른 건 검색 결과가 아니라 "이미 정해진 후보"라
  // AI 호출(match/recommend, 한도 적용)이 아니라 LLM을 쓰지 않는 /goal/feasibility만
  // 부른다 — 한도 초과 화면에서 골라도 바로 걸리지 않고 기간 계산까지 볼 수 있다.
  function pickPopularGoal(candidate) {
    setProvisionalPick(candidate);
    setPickOrigin(view); // 'suggested' 또는 'limited' — "이전"에서 여기로 돌아오게
    setView('time');
  }

  // ── STEP 2 → 3: 가용시간 입력 후 추천 요청 (FR-GOAL-02 → 03·04·05·09) ──
  async function handleTimeNext() {
    setExcludedCandidates([]);

    if (provisionalPick) {
      setView('matching');
      setBusy(true);
      setError('');
      try {
        const res = await api.goal.feasibility({ candidates: [provisionalPick], weeklyHours });
        const feasibleOnes = res.candidates || [];
        if (!res.all_exceeded && feasibleOnes.length > 0) {
          // 사용자가 인기 목록에서 이미 "이 목표로 할래요"라고 콕 집어 골랐고, 기한도
          // 맞는다. "이 중에 해볼 만한 게 있나요?" 화면은 여러 후보 중 고르라는
          // 뜻이라 이미 고른 걸 다시 보여주며 관심있음/없음을 묻는 건 어색하다 —
          // 바로 확정 화면으로 넘긴다. (사용자 피드백: "목표 확정 화면이 바로
          // 보여야 하는거 아니야?")
          const g = feasibleOnes[0];
          sendFeedback(g, true);
          setPicked({
            title: g.title,
            minWeeks: g.min_weeks,
            recommendedWeeks: g.recommended_weeks,
            weeklyHours: g.weekly_hours,
            source: 'popular_pick',
          });
          setView('confirm');
        } else {
          // 기한을 못 맞추면(all_exceeded) 이유를 보여줘야 하니 recommend 화면의
          // EmptyState로 보낸다 — 여기서만 "이 중에 해볼 만한 게 있나요?" 화면을 쓴다.
          setCandidates(feasibleOnes);
          setQueryUsed('popular_pick');
          setAllExceeded(!!res.all_exceeded);
          setExcludedCandidates(res.excluded || []);
          setView('recommend');
        }
      } catch (err) {
        setError(err.message || '요청이 실패했습니다.');
        setView('time');
      } finally {
        setBusy(false);
        // provisionalPick은 여기서 지우지 않는다. recommend에서 "이전"으로 time까지
        // 돌아왔다가(둘 다 provisionalPick을 건드리지 않는다) 시간만 바꿔서 "다음"을
        // 다시 누르면, 지웠을 경우 이 분기를 타지 못하고 아래 태그 검색(tags=[])으로
        // 빠져 버려 방금 고른 인기 목표 대신 전혀 다른 fallback_popular 결과가 나온다
        // (실제로 이 버그로 재현됨). provisionalPick은 오직 태그 경로로 정상 진행하는
        // 두 지점(handleInterestNext, suggested 화면의 "다음")에서만 지운다.
      }
      return;
    }

    setView('matching');
    // 칩으로 고른 tags뿐 아니라 자유입력(freeText)에서 뽑아낸 단어도 함께 검색한다.
    const searchTags = [...new Set([...tags, ...freeTextTokens(freeText)])];
    const res = await runLimited(
      () => api.goal.recommend({ tags: searchTags, weeklyHours, sessionId: getAnonSessionId() }),
      'time'
    );
    if (!res) {
      // 한도 초과라면 runLimited가 이미 'limited'로 바꿔놨으니 덮어쓰지 않는다.
      if (!lastLimitedRef.current) setView('time');
      return;
    }
    setCandidates(res.candidates || []);
    setQueryUsed(res.query_used);
    setAllExceeded(!!res.all_exceeded);
    setExcludedCandidates(res.excluded || []);
    setView('recommend');
  }

  // 화면 표시 전용 계산. excluded 후보(서버가 이미 min_weeks·standard_hours·deadline까지
  // 계산해 준 FeasibleCandidate)에서 "마감까지 남은 기간"만 화면 설명용으로 추가 계산한다.
  // 통과/탈락 판정 자체는 여전히 서버(feasible/all_exceeded)가 내린 값을 그대로 쓴다.
  function deadlineWeeksLeft(candidate) {
    if (!candidate?.deadline) return null;
    const days = (new Date(candidate.deadline) - new Date()) / (1000 * 60 * 60 * 24);
    return Math.max(Math.round((days / 7) * 10) / 10, 0);
  }

  // excluded 후보 목록으로 "왜 기한을 맞추기 어려운지" 문구를 만든다.
  // 후보 1건이면 표준시간·최소기간·마감일까지 구체적으로, 여러 건이면 이름만 나열한다.
  function excludedDetailText(list) {
    if (!list || list.length === 0) return '';
    if (list.length === 1) {
      const c = list[0];
      const weeksLeft = deadlineWeeksLeft(c);
      return (
        `'${c.title}'은(는) 보통 ${c.standard_hours}시간(약 ${c.min_weeks}주)이 필요해요.` +
        (c.deadline ? ` 다음 응시 가능일(${c.deadline})까지 남은 기간은 약 ${weeksLeft}주라 부족해요.` : '')
      );
    }
    const titles = list.map((c) => c.title).join(', ');
    return `${titles}은(는) 지금 가용시간으로는 기한 안에 어려워 제외했어요.`;
  }

  // ── STEP 3: 추천 카드 피드백 (FR-GOAL-08) ──────────────────
  async function sendFeedback(candidate, interested, reason = null) {
    // "관심 없음"만 목록에서 숨긴다. "관심 있음"으로 확정 화면에 갔다가 "이전"으로
    // 돌아왔을 때 방금 고른 카드까지 사라지면 안 되므로 숨김 처리는 하지 않는다.
    if (!interested) {
      setFeedbackDone((prev) => ({ ...prev, [candidate.goal_id]: true }));
    }
    setReasonPromptFor(null);
    try {
      await api.goal.feedback({
        goalId: candidate.goal_id,
        interested,
        reason,
        sessionId: getAnonSessionId(),
      });
    } catch {
      /* 저장 실패로 흐름을 막지 않는다 — FR-GOAL-08 세부사항: 로컬 큐 대신 조용히 넘어간다 */
    }
  }

  function selectCandidate(candidate) {
    sendFeedback(candidate, true);
    setPicked({
      title: candidate.title,
      minWeeks: candidate.min_weeks,
      recommendedWeeks: candidate.recommended_weeks,
      weeklyHours: candidate.weekly_hours,
      source: 'recommend',
    });
    setView('confirm');
  }

  // ── STEP 3-대체: 목표 직접 입력 (FR-GOAL-06) ────────────────
  async function handleManualNext() {
    if (
      manualGoal.title.trim().length < 2 ||
      !manualGoal.dueDate ||
      !manualGoal.weeklyHours ||
      Number(manualGoal.weeklyHours) <= 0
    ) {
      setError('목표명(2자 이상), 기한, 주당 목표 시간(1시간 이상)을 모두 입력해 주세요.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const warning = await api.goal.manualCheck({
        title: manualGoal.title,
        dueDate: manualGoal.dueDate,
        weeklyHours: Number(manualGoal.weeklyHours),
      });
      setManualWarning(warning);
      setView('manual-warn');
    } catch (err) {
      setError(err.message || '요청이 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  function confirmManualGoal() {
    setPicked({
      title: manualGoal.title,
      minWeeks: manualWarning?.min_weeks ?? null,
      recommendedWeeks: manualWarning?.recommended_weeks ?? null,
      weeklyHours: Number(manualGoal.weeklyHours),
      source: 'manual',
    });
    setView('confirm');
  }

  // ── STEP 4: 목표 확정 (FR-GOAL-07) ──────────────────────────
  async function handleConfirm() {
    setBusy(true);
    setError('');
    try {
      // TODO: 로그인 상태를 실제로 읽어오는 인증 붙으면 isMember 를 그 값으로 바꾼다.
      const res = await api.goal.confirm({ goalTitle: picked.title, isMember: false, activeGoalCount: 0 });
      if (res.requires_closing_goal) {
        setError(res.message);
        return;
      }
      // FR-GOAL-13 — 가입 후 이어받을 수 있도록 세션에 저장해 둔다 (30분 유효)
      saveExploration({ tags, weeklyHours, slots, picked });
      router.push('/signup');
    } catch (err) {
      setError(err.message || '요청이 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  const step = STEP_OF_VIEW[view] || 1;
  // recommend 화면에서 "관심없음"으로 전부 숨겨진 뒤에도 candidates 자체는 그대로라
  // candidates.length만으로는 "서버가 원래 없다고 했다"와 "다 치워서 없다"를 구분하지
  // 못한다. 화면에 실제로 보여줄 목록은 이 값으로 판단한다.
  const visibleCandidates = candidates.filter((g) => !feedbackDone[g.goal_id]);
  const allDismissed = candidates.length > 0 && visibleCandidates.length === 0;

  // FR-GOAL-01 관심분야 선택으로 처음부터 다시 시작 (인기 목표 직접 고르기 경로도 리셋)
  function restartInterest() {
    setProvisionalPick(null);
    setPickOrigin('interest');
    setTags([]);
    setFreeText('');
    setView('interest');
  }

  return (
    <div className="focus">
      <main className="shell page" style={{ paddingBottom: 'var(--gap-6)' }}>
        {view !== 'limited' && (
          <header className="stack" style={{ gap: 'var(--gap-3)', paddingTop: 'var(--gap-4)' }}>
            <div className="stepper">
              {[1, 2, 3, 4].map((n) => (
                <span key={n} className={n <= step ? 'stepper-dot on' : 'stepper-dot'} />
              ))}
            </div>
            <div>
              <p className="dim tiny mono">STEP {step} / 4</p>
              <h1 style={{ fontSize: 21, marginTop: 4 }}>
                {view === 'interest' && '어떤 분야에 관심이 있나요?'}
                {view === 'suggested' && '이런 분야는 어떠세요?'}
                {view === 'time' && '언제 공부할 수 있나요?'}
                {view === 'matching' && '목표를 찾고 있어요'}
                {view === 'recommend' &&
                  (allDismissed
                    ? '다른 방법을 찾아볼까요?'
                    : visibleCandidates.length === 0
                    ? // 후보가 하나도 안 남았는데(서버가 애초에 못 찾음/전부 기한초과) "이 중에
                      // 해볼 만한 게 있나요?"라고 물으면 내용과 타이틀이 어긋난다. 아래
                      // EmptyState 제목과 같은 문구로 맞춘다. (사용자 피드백: 타이틀/내용 불일치)
                      allExceeded
                      ? '가용시간으로는 기한을 맞추기 어려워요'
                      : '추천할 목표를 찾지 못했어요'
                    : '이 중에 해볼 만한 게 있나요?')}
                {view === 'manual' && '목표를 직접 입력할게요'}
                {view === 'manual-warn' && '기한을 확인해 주세요'}
                {view === 'confirm' && '이 목표로 확정할까요?'}
              </h1>
            </div>
          </header>
        )}

        {error && <p className="hint hint-error">{error}</p>}

        {/* ── FR-GOAL-01 ── */}
        {view === 'interest' && (
          <section className="stack" style={{ gap: 'var(--gap-4)' }}>
            <p className="muted" style={{ fontSize: 14 }}>
              최대 5개까지 고를 수 있어요. 잘 모르겠으면 건너뛰어도 됩니다.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--gap-2)' }}>
              {availableTags.map((tag) => (
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
              <input
                id="free"
                className="input"
                maxLength={100}
                placeholder="예) 데이터 분석 쪽으로 취업하고 싶어요"
                value={freeText}
                onChange={(e) => setFreeText(e.target.value)}
              />
            </div>
          </section>
        )}

        {/* ── FR-GOAL-11 ── */}
        {view === 'suggested' && (
          <section className="stack" style={{ gap: 'var(--gap-4)' }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className="pill pill-ai mono">AI 제안</span>
              <p className="muted tiny">확정은 아니에요. 눌러서 골라도 되고, 그냥 넘어가도 돼요.</p>
            </div>

            {suggestedTags.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--gap-2)' }}>
                {suggestedTags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    className="chip"
                    aria-pressed={tags.includes(tag)}
                    onClick={() => toggleSuggestedTag(tag)}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            )}

            {popularGoals.length > 0 && (
              <div className="stack" style={{ gap: 'var(--gap-2)' }}>
                <p className="tiny strong">이력이 없다면, 지금 인기 있는 목표 (눌러서 바로 골라도 돼요)</p>
                <ul className="list">
                  {popularGoals.map((g) => (
                    <li
                      key={g.goal_id}
                      className="row row-clickable"
                      role="button"
                      tabIndex={0}
                      onClick={() => pickPopularGoal(g)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          pickPopularGoal(g);
                        }
                      }}
                    >
                      <span>
                        <b>{g.title}</b>
                        <span className="dim tiny" style={{ marginLeft: 8 }}>
                          {g.standard_hours}시간 분량
                        </span>
                      </span>
                      <span className="pill mono">{g.popularity}명 도전 중</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {suggestedTags.length === 0 && popularGoals.length === 0 && (
              <EmptyState title="아직 보여드릴 만한 이력이 없어요" description="그냥 다음으로 넘어가도 괜찮아요." />
            )}
          </section>
        )}

        {/* ── FR-GOAL-02 ── */}
        {view === 'time' && (
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

        {/* ── FR-GOAL-03 진행 상태 ── */}
        {view === 'matching' && (
          <section className="stack" style={{ gap: 'var(--gap-4)', alignItems: 'center', textAlign: 'center', padding: 'var(--gap-6) 0' }}>
            <span className="pill pill-ai mono">RAG 검색</span>
            <p style={{ fontSize: 15, fontWeight: 600 }}>관심분야에 맞는 목표를 찾고 있어요</p>
            <p className="muted tiny">자격증 · 공모전 후보를 분석하는 중...</p>
          </section>
        )}

        {/* ── FR-GOAL-05 · FR-GOAL-08 ── */}
        {view === 'recommend' && (
          <section className="stack" style={{ gap: 'var(--gap-3)' }}>
            <p className="muted" style={{ fontSize: 14 }}>
              {allDismissed ? (
                // 후보가 있긴 했지만 전부 "관심없음"으로 치웠다 — "~목표만 남겼습니다"는
                // 어긋나는 문구라 별도로 안내한다. (사용자 피드백: 화면 타이틀/내용 불일치)
                <>보여드린 후보를 모두 넘기셨어요. 관심분야를 다시 고르거나 직접 입력해 보세요.</>
              ) : visibleCandidates.length > 0 ? (
                <>
                  입력하신 주 {weeklyHours}시간으로 <b>기한 안에 끝낼 수 있는 목표만</b> 남겼습니다.
                  {queryUsed === 'fallback_popular' && ' 딱 맞는 후보가 없어 인기 목록으로 대신 보여드려요.'}
                  {queryUsed === 'popular_pick' && ' 고르신 목표로 기간을 계산했어요.'}
                </>
              ) : (
                // candidates가 비어있는데 "~목표만 남겼습니다"라고 하면 화면 내용과 문구가
                // 어긋난다(뭘 남겼다는 건지 알 수 없음). 아래 EmptyState가 이유를 설명하므로
                // 여기서는 "찾지 못했다"는 사실만 짧게 알린다.
                <>입력하신 주 {weeklyHours}시간 기준으로는 기한 안에 끝낼 수 있는 목표를 찾지 못했습니다.</>
              )}
            </p>

            {allDismissed ? (
              <EmptyState
                title="다 넘기셨네요"
                description="관심분야를 다시 골라 새로 추천받거나, 원하는 목표를 직접 입력해 보세요."
                action={
                  <div className="stack" style={{ gap: 'var(--gap-2)' }}>
                    <button type="button" className="btn btn-sm" onClick={restartInterest}>
                      관심분야 다시 고르기
                    </button>
                    <button type="button" className="btn btn-sm btn-primary" onClick={() => setView('manual')}>
                      직접 입력할래요
                    </button>
                  </div>
                }
              />
            ) : visibleCandidates.length === 0 ? (
              <EmptyState
                title={allExceeded ? '가용시간으로는 기한을 맞추기 어려워요' : '추천할 목표를 찾지 못했어요'}
                description={
                  allExceeded
                    ? excludedCandidates.length
                      ? `${excludedDetailText(excludedCandidates)} 가용시간을 늘리거나, 범위를 줄여 직접 입력해 보세요.`
                      : '가용시간을 늘리거나, 범위를 줄여 직접 입력해 보세요.'
                    : '직접 목표를 입력해 볼 수 있어요.'
                }
                action={
                  <div className="stack" style={{ gap: 'var(--gap-2)' }}>
                    <button type="button" className="btn btn-sm" onClick={() => setView('time')}>
                      가용시간 다시 정하기
                    </button>
                    <button type="button" className="btn btn-sm" onClick={restartInterest}>
                      관심분야 다시 고르기
                    </button>
                    <button type="button" className="btn btn-sm btn-primary" onClick={() => setView('manual')}>
                      직접 입력할래요
                    </button>
                  </div>
                }
              />
            ) : (
              <>
                {excludedCandidates.length > 0 && (
                  <div
                    className="hint"
                    style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 12px' }}
                  >
                    <p style={{ margin: 0, fontSize: 13 }}>{excludedDetailText(excludedCandidates)}</p>
                    <button
                      type="button"
                      className="btn btn-sm"
                      style={{ marginTop: 8 }}
                      onClick={() => setView('time')}
                    >
                      가용시간 다시 정하기
                    </button>
                  </div>
                )}
                <ul className="list">
                {visibleCandidates
                  .map((g) => (
                    <li key={g.goal_id} className="ct">
                      <div style={{ display: 'flex', gap: 'var(--gap-2)', marginBottom: 8, flexWrap: 'wrap' }}>
                        {g.ai_generated ? <AiBadge /> : <span className="pill mono">인기 목표</span>}
                        <span className="pill mono">{g.min_weeks}주 예상</span>
                        <span className="pill mono">주 {g.weekly_hours}시간</span>
                      </div>
                      <b style={{ fontSize: 16 }}>{g.title}</b>
                      {g.reason && <p className="ct-reason">{g.reason}</p>}

                      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                        <button type="button" className="btn btn-sm btn-primary" onClick={() => selectCandidate(g)}>
                          관심 있음
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-quiet btn-quiet-hover"
                          onClick={() => setReasonPromptFor(g.goal_id)}
                        >
                          관심 없음
                        </button>
                      </div>

                      {reasonPromptFor === g.goal_id && (
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                          {FEEDBACK_REASONS.map((r) => (
                            <button
                              key={r.id}
                              type="button"
                              className="chip"
                              onClick={() => sendFeedback(g, false, r.id)}
                            >
                              {r.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}

            <AiNotice>
              추천 목표와 예상 기간은 AI가 생성하며 부정확할 수 있습니다. 시험일과 응시 자격은 직접 확인해 주세요.
            </AiNotice>

            {/* EmptyState(위 두 분기)에는 이미 "직접 입력할래요"/"관심분야 다시 고르기"가
                버튼으로 들어있다 — 여기서 또 보여주면 같은 동작이 화면에 두 번 나온다
                (사용자 피드백: 중복 버튼). 카드 목록이 실제로 보일 때만 노출한다. */}
            {visibleCandidates.length > 0 && (
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn btn-quiet btn-quiet-hover"
                style={{ fontSize: 13, width: 'auto' }}
                onClick={() => setView('manual')}
              >
                추천 대신 목표를 직접 입력할래요
              </button>
              <button
                type="button"
                className="btn btn-quiet btn-quiet-hover"
                style={{ fontSize: 13, width: 'auto' }}
                onClick={restartInterest}
              >
                관심분야 다시 고르기
              </button>
            </div>
            )}
          </section>
        )}

        {/* ── FR-GOAL-06 ── */}
        {view === 'manual' && (
          <section className="stack" style={{ gap: 'var(--gap-4)' }}>
            <p className="muted" style={{ fontSize: 14 }}>추천을 쓰지 않고 원하는 목표를 등록해요.</p>

            <div className="field">
              <label htmlFor="mg-title">목표명</label>
              <input
                id="mg-title"
                className="input"
                minLength={2}
                maxLength={40}
                value={manualGoal.title}
                onChange={(e) => setManualGoal((p) => ({ ...p, title: e.target.value }))}
                placeholder="예) 정보보안기사 실기"
              />
            </div>
            <div className="field">
              <label htmlFor="mg-due">기한</label>
              <input
                id="mg-due"
                type="date"
                className="input"
                min={new Date().toISOString().slice(0, 10)}
                value={manualGoal.dueDate}
                onChange={(e) => setManualGoal((p) => ({ ...p, dueDate: e.target.value }))}
              />
            </div>
            <div className="field">
              <label htmlFor="mg-hours">주당 목표 시간</label>
              <input
                id="mg-hours"
                type="number"
                min="1"
                className="input"
                value={manualGoal.weeklyHours}
                onChange={(e) => setManualGoal((p) => ({ ...p, weeklyHours: e.target.value }))}
                placeholder="예) 6"
              />
            </div>

            <p className="hint">카탈로그에 없는 목표는 학습 계획의 추정 비중이 커질 수 있어요.</p>
          </section>
        )}

        {/* ── FR-GOAL-10 ── */}
        {view === 'manual-warn' && manualWarning && (
          <section className="stack" style={{ gap: 'var(--gap-4)' }}>
            <div
              className="panel"
              style={{
                padding: 'var(--gap-4)',
                borderColor: manualWarning.severity === 'danger' ? 'var(--late)' : 'var(--rule)',
              }}
            >
              <p style={{ fontWeight: 700, marginBottom: 6 }}>{manualWarning.message}</p>
              {manualWarning.severity !== 'unknown' && (
                <div className="stack" style={{ gap: 4 }}>
                  <div className="row">
                    <span className="muted tiny">최소 필요 기간</span>
                    <span className="mono">{manualWarning.min_weeks}주</span>
                  </div>
                  <div className="row">
                    <span className="muted tiny">권장 기간</span>
                    <span className="mono">{manualWarning.recommended_weeks}주</span>
                  </div>
                  <div className="row" style={{ borderBottom: 'none' }}>
                    <span className="muted tiny">입력하신 기한</span>
                    <span className="mono strong">{manualWarning.requested_weeks}주</span>
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ── FR-GOAL-07 ── */}
        {view === 'confirm' && picked && (
          <section className="stack" style={{ gap: 'var(--gap-4)' }}>
            <div className="panel" style={{ padding: 'var(--gap-4)' }}>
              <b style={{ fontSize: 16 }}>{picked.title}</b>
              <div style={{ display: 'flex', gap: 14, marginTop: 8 }}>
                {picked.minWeeks != null && picked.minWeeks >= 0 && (
                  <span className="mono tiny muted">예상 {picked.minWeeks}주</span>
                )}
                <span className="mono tiny muted">주 {picked.weeklyHours}시간</span>
              </div>
            </div>
            <p className="hint">동시 진행 목표는 최대 2개까지예요.</p>
          </section>
        )}

        {/* ── FR-GOAL-12 ── */}
        {view === 'limited' && (
          <LimitedView
            message={limitMessage}
            onBack={() => setView(limitOrigin)}
            onPick={pickPopularGoal}
          />
        )}

        {/* ── 하단 내비게이션 ── */}
        {view !== 'limited' && (
          <div className="stack" style={{ gap: 'var(--gap-2)' }}>
            {view === 'interest' && (
              <>
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => handleInterestNext()}>
                  {busy ? '불러오는 중...' : '다음'}
                </button>
                <button
                  type="button"
                  className="btn btn-quiet"
                  disabled={busy}
                  onClick={() => handleInterestNext(true)}
                >
                  입력 없이 건너뛰기
                </button>
              </>
            )}

            {view === 'suggested' && (
              <>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => {
                    setProvisionalPick(null); // 태그로 정상 진행 — 남은 인기 목표 단건 선택은 무시
                    setPickOrigin('interest'); // "이전"이 이 화면(suggested)이 아니라 처음으로 돌아가게
                    setView('time');
                  }}
                >
                  다음
                </button>
                <button type="button" className="btn btn-quiet" onClick={() => setView('interest')}>
                  이전
                </button>
              </>
            )}

            {view === 'time' && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || weeklyHours === 0}
                onClick={handleTimeNext}
              >
                {busy ? '찾는 중...' : '다음'}
              </button>
            )}

            {view === 'manual' && (
              <button type="button" className="btn btn-primary" disabled={busy} onClick={handleManualNext}>
                {busy ? '확인하는 중...' : '다음'}
              </button>
            )}

            {view === 'manual-warn' && (
              <button type="button" className="btn btn-primary" onClick={confirmManualGoal}>
                {manualWarning?.severity === 'danger' || manualWarning?.severity === 'warn'
                  ? '그래도 이대로 진행하기'
                  : '확정하러 가기'}
              </button>
            )}

            {view === 'confirm' && (
              <>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={handleConfirm}
                >
                  {busy ? '확정하는 중...' : '가입하고 일정 만들기'}
                </button>
                <p className="hint" style={{ textAlign: 'center' }}>
                  일정 저장에는 가입이 필요합니다 · 방금 고른 값은 그대로 이어집니다
                </p>
              </>
            )}

            {['time', 'recommend', 'manual', 'manual-warn', 'confirm'].includes(view) && (
              <button
                type="button"
                className="btn btn-quiet btn-quiet-hover"
                // pickOrigin은 태그 경로로 정상 진행할 때만 'interest'로 리셋되고, 그 외엔
                // 계속 남아있는 값이라 provisionalPick 유무를 따로 확인할 필요 없이 항상
                // 이 값을 그대로 쓴다.
                onClick={() => setView(backTargetFor(view, picked, pickOrigin, allDismissed))}
              >
                이전
              </button>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

// 각 화면에서 "이전"을 눌렀을 때 돌아갈 화면.
// confirm 은 추천 카드를 골랐는지 직접 입력을 골랐는지에 따라 되돌아갈 곳이 다르다.
// pickOrigin 은 기본값이 'interest'이고, 인기 목표를 직접 골랐을 때만 그 고르기 전 화면
// ('suggested'/'limited')으로 바뀐다 — 'time'의 "이전"이 그 화면으로 돌아가게 해 준다.
// allDismissed(recommend 화면에서 후보를 전부 "관심없음"으로 치운 상태)일 때는 시간이
// 문제가 아니라 지금 관심분야로는 더 보여줄 게 없다는 뜻이라, "이전"도 시간 설정이
// 아니라 관심분야를 다시 고르던 화면으로 보낸다 (사용자 피드백: "이전 누르면 시간설정
// 화면으로 가는데 바꿔야 할 듯").
function backTargetFor(view, picked, pickOrigin, allDismissed = false) {
  switch (view) {
    case 'time':
      return pickOrigin || 'interest';
    case 'recommend':
      return allDismissed ? pickOrigin || 'interest' : 'time';
    case 'manual':
      return 'recommend';
    case 'manual-warn':
      return 'manual';
    case 'confirm':
      if (picked?.source === 'manual') return 'manual-warn';
      // popular_pick은 recommend 화면을 아예 거치지 않고 바로 confirm으로 왔으므로
      // "이전"도 recommend가 아니라 시간 설정 화면으로 돌려보낸다.
      if (picked?.source === 'popular_pick') return 'time';
      return 'recommend';
    default:
      return 'interest';
  }
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

// FR-GOAL-12 — 비회원 AI 호출 한도 화면. 인기 목록·공모전 검색은 계속 열려 있다.
function LimitedView({ message, onBack, onPick }) {
  const [popular, setPopular] = useState(null);

  useEffect(() => {
    api.goal
      .popular(3)
      .then((res) => setPopular(res.goals || []))
      .catch(() => setPopular([]));
  }, []);

  return (
    <section className="stack" style={{ gap: 'var(--gap-4)', paddingTop: 'var(--gap-5)' }}>
      <EmptyState
        title="오늘 추천 횟수를 다 썼어요"
        description={message || '비회원은 24시간 동안 AI 추천을 3번까지 받을 수 있어요.'}
      />

      {popular && popular.length > 0 && (
        <div className="stack" style={{ gap: 'var(--gap-2)' }}>
          <p className="tiny strong">그래도 볼 수 있는 인기 목표 (눌러서 바로 골라도 돼요)</p>
          <ul className="list">
            {popular.map((g) => (
              <li
                key={g.goal_id}
                className="row row-clickable"
                role="button"
                tabIndex={0}
                onClick={() => onPick(g)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onPick(g);
                  }
                }}
              >
                <b>{g.title}</b>
                <span className="pill mono">{g.popularity}명 도전 중</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Link href="/signup" className="btn btn-primary">
        가입하고 무제한으로 추천받기
      </Link>
      <button type="button" className="btn btn-quiet" onClick={onBack}>
        이전으로
      </button>
    </section>
  );
}
