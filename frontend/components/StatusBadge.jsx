const STATUS_STYLES = {
  pending: { label: 'Pending', color: '#f97316', dot: '#fb923c' },
  running: { label: 'Running', color: '#2563eb', dot: '#60a5fa' },
  awaiting_approval: { label: 'Awaiting Approval', color: '#9333ea', dot: '#c084fc' },
  completed: { label: 'Completed', color: '#16a34a', dot: '#4ade80' },
  failed: { label: 'Failed', color: '#dc2626', dot: '#f87171' },
};

export default function StatusBadge({ status }) {
  const metadata = STATUS_STYLES[status] || STATUS_STYLES.pending;

  return (
    <span className="badge" style={{ backgroundColor: `${metadata.dot}22`, color: metadata.color }}>
      <span style={{ backgroundColor: metadata.dot }} />
      {metadata.label}
    </span>
  );
}
