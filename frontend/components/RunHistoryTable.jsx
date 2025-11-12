'use client';

import StatusBadge from './StatusBadge';

// Normalizes timestamps to the viewer locale.
function formatDate(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch (error) {
    return value;
  }
}

export default function RunHistoryTable({
  analyses = [],
  selectedId,
  onSelect,
  isLoading,
  onRefresh,
  lastUpdated,
}) {
  // Any consumer can quickly glance at the control header to understand refresh cadence.
  return (
    <div className="card">
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '1rem',
        }}
      >
        <div>
          <h2 style={{ marginBottom: '0.25rem' }}>Run history</h2>
          <p style={{ color: 'var(--color-text-muted)', margin: 0 }}>
            Track LangGraph executions and drill into artifact output.
          </p>
        </div>
        <div className="form-actions" style={{ justifyContent: 'flex-end' }}>
          <button
            type="button"
            className="secondary-button"
            onClick={onRefresh}
            disabled={isLoading}
          >
            {isLoading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
      <p className="refresh-indicator" style={{ marginTop: '0.75rem' }}>
        Last updated {lastUpdated ? formatDate(lastUpdated) : 'never'}
      </p>
      <div className="table-container" style={{ marginTop: '1rem' }}>
        <table className="table">
          <thead>
            <tr>
              <th style={{ minWidth: '180px' }}>Analysis ID</th>
              <th>Email</th>
              <th>Status</th>
              <th>Updated</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {analyses.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="table-empty"
                  style={{ textAlign: 'center', padding: '2rem' }}
                >
                  {isLoading ? 'Loading runs...' : 'No runs recorded yet.'}
                </td>
              </tr>
            )}
            {analyses.map((analysis) => {
              const isSelected = analysis.analysisId === selectedId;
              const handleKeyDown = (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(analysis.analysisId);
                }
              };
              return (
                <tr
                  key={analysis.analysisId}
                  className={isSelected ? 'selected' : ''}
                  onClick={() => onSelect(analysis.analysisId)}
                  tabIndex={0}
                  role="button"
                  aria-pressed={isSelected}
                  onKeyDown={handleKeyDown}
                >
                  <td style={{ fontFamily: 'monospace' }}>{analysis.analysisId}</td>
                  <td>{analysis.email}</td>
                  <td>
                    <StatusBadge status={analysis.status} />
                  </td>
                  <td>{formatDate(analysis.updatedAt)}</td>
                  <td style={{ maxWidth: '240px' }}>
                    {analysis.lastError ? (
                      <span style={{ color: 'var(--color-error)' }}>{analysis.lastError}</span>
                    ) : (
                      <span style={{ color: 'var(--color-text)', opacity: 0.45 }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
