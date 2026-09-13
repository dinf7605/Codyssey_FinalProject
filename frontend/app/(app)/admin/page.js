import SectionTitle from '@/components/SectionTitle';

// FR-ADMIN-01 수집 공고 점검 / FR-ADMIN-02 AI 호출 모니터링
// 일일 비용 임계치를 넘으면 신규 AI 호출을 차단한다 (NFR-COST-01).

const USAGE = [
  { feature: '목표 추천', calls: 128, fail: 2, cost: '$0.42' },
  { feature: '학습 분해', calls: 64, fail: 1, cost: '$1.18' },
  { feature: '추천 이유', calls: 310, fail: 0, cost: '$0.21' },
];

export default function AdminPage() {
  const total = USAGE.reduce((s, u) => s + u.calls, 0);

  return (
    <>
      <header className="stack" style={{ gap: 4 }}>
        <h1 style={{ fontSize: 20 }}>관리자</h1>
        <p className="muted tiny">오늘 AI 호출 {total}건</p>
      </header>

      <section>
        <SectionTitle>AI 사용량</SectionTitle>
        <div className="rows">
          {USAGE.map((u) => (
            <div className="row" key={u.feature}>
              <div className="row-main">
                <b>{u.feature}</b>
                <span>호출 {u.calls}건 · 실패 {u.fail}건</span>
              </div>
              <span className="mono tiny">{u.cost}</span>
            </div>
          ))}
        </div>
        <p className="hint" style={{ marginTop: 'var(--gap-2)' }}>
          일일 비용 임계치 초과 시 신규 AI 호출을 차단하고 비AI 기능은 유지합니다
        </p>
      </section>

      <section>
        <SectionTitle>수집 공고 점검</SectionTitle>
        <div className="rows">
          <div className="row">
            <div className="row-main">
              <b>마감일 누락</b>
              <span>파싱 실패로 검수가 필요한 공고</span>
            </div>
            <span className="pill mono" style={{ color: 'var(--warn)' }}>3건</span>
          </div>
          <div className="row">
            <div className="row-main">
              <b>중복 의심</b>
              <span>주최 + 제목 + 마감일이 유사한 공고</span>
            </div>
            <span className="pill mono">1건</span>
          </div>
          <div className="row">
            <div className="row-main">
              <b>미색인</b>
              <span>임베딩 실패 · 다음 배치에서 재처리</span>
            </div>
            <span className="pill mono">0건</span>
          </div>
        </div>
      </section>
    </>
  );
}
