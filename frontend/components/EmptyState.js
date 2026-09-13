export default function EmptyState({ title, description, action }) {
  return (
    <div className="empty">
      <p style={{ fontWeight: 600 }}>{title}</p>
      {description && <p className="muted tiny" style={{ maxWidth: '30ch' }}>{description}</p>}
      {action && <div style={{ marginTop: 6 }}>{action}</div>}
    </div>
  );
}
