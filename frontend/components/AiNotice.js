// NFR-ETHIC-01 — AI가 만든 내용에는 반드시 배지와 고지 문구를 붙인다.
// 접거나 숨길 수 없어야 하므로 토글 기능을 일부러 넣지 않았다.

export function AiBadge() {
  return <span className="pill pill-ai">AI 추천</span>;
}

export function AiNotice({ children }) {
  return (
    <p className="ai-notice">
      <span aria-hidden="true">※</span>
      <span>
        {children ||
          'AI가 생성한 내용이라 부정확할 수 있습니다. 지원 자격과 마감일은 원문에서 확인해 주세요.'}
      </span>
    </p>
  );
}
