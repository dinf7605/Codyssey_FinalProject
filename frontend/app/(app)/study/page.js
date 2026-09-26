import StudyTimer from '@/components/StudyTimer';

// FR-STUDY-01 학습 타이머 / FR-STUDY-02 블록 완료 처리 / FR-STUDY-05 학습 메모 — 실제 API (담당 C)
// /study?block=<블록 id> 로 들어오면 그 블록을, 없으면 오늘 남은 첫 블록을 잰다.

export default async function StudyPage({ searchParams }) {
  const { block } = await searchParams;
  return <StudyTimer blockId={typeof block === 'string' ? block : null} />;
}
