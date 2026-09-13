// 빈 상태를 그냥 비워두지 않는다.
// 기능명세서의 '결과 0건' 예외 처리가 대부분 이 컴포넌트로 표현된다.

export default function EmptyState({ title, description, action }) {
  return (
    <div className="card empty">
      <p className="strong">{title}</p>
      {description && <p className="muted tiny empty-desc">{description}</p>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}
