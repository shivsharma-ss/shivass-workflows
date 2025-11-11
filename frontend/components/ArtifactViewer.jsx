'use client';

import StatusBadge from './StatusBadge';

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

function renderJson(content) {
  if (typeof content !== 'string') {
    return JSON.stringify(content, null, 2);
  }
  try {
    const parsed = JSON.parse(content);
    return JSON.stringify(parsed, null, 2);
  } catch (error) {
    return content;
  }
}

export default function ArtifactViewer({ summary, detail, artifacts, isLoading }) {
  if (!summary) {
    return (
      <div className="card" style={{ minHeight: '320px' }}>
        <h2>Run details</h2>
        <p style={{ color: '#64748b' }}>Select a run from the history to inspect payloads and artifacts.</p>
      </div>
    );
  }

  return (
    <div className="card" style={{ minHeight: '320px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
        <div>
          <h2 style={{ marginBottom: '0.25rem' }}>Run details</h2>
          <p style={{ color: '#475569', margin: 0 }}>Inspect structured payloads saved during execution.</p>
        </div>
        <StatusBadge status={summary.status} />
      </div>

      <div className="status-grid" style={{ marginTop: '1.5rem' }}>
        <div className="status-card">
          <strong>Analysis ID</strong>
          <div style={{ fontFamily: 'monospace', marginTop: '0.25rem' }}>{summary.analysisId}</div>
        </div>
        <div className="status-card">
          <strong>Email</strong>
          <div style={{ marginTop: '0.25rem' }}>{summary.email}</div>
        </div>
        <div className="status-card">
          <strong>CV doc ID</strong>
          <div style={{ fontFamily: 'monospace', marginTop: '0.25rem' }}>{summary.cvDocId}</div>
        </div>
        <div className="status-card">
          <strong>Created</strong>
          <div style={{ marginTop: '0.25rem' }}>{formatDate(summary.createdAt)}</div>
        </div>
        <div className="status-card">
          <strong>Updated</strong>
          <div style={{ marginTop: '0.25rem' }}>{formatDate(summary.updatedAt)}</div>
        </div>
      </div>

      {detail?.lastError && (
        <div className="alert error" style={{ marginTop: '1.5rem' }}>
          Last error: {detail.lastError}
        </div>
      )}

      <div style={{ marginTop: '1.5rem' }}>
        <h3 style={{ marginBottom: '0.75rem' }}>Latest workflow payload</h3>
        {detail ? (
          <pre>{renderJson(detail.payload || {})}</pre>
        ) : (
          <p style={{ color: '#64748b' }}>{isLoading ? 'Loading payload...' : 'No payload recorded yet.'}</p>
        )}
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <h3 style={{ marginBottom: '0.75rem' }}>Artifacts</h3>
        {isLoading && artifacts.length === 0 ? (
          <p style={{ color: '#64748b' }}>Loading artifacts...</p>
        ) : artifacts.length === 0 ? (
          <p style={{ color: '#64748b' }}>No artifacts have been persisted for this run.</p>
        ) : (
          <div className="artifact-list">
            {artifacts.map((artifact) => (
              <div key={`${artifact.artifactType}-${artifact.createdAt}`} className="artifact-item">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '0.75rem' }}>
                  <h4 style={{ marginBottom: 0 }}>{artifact.artifactType}</h4>
                  <span className="refresh-indicator">{formatDate(artifact.createdAt)}</span>
                </div>
                <pre style={{ marginTop: '0.75rem' }}>{renderJson(artifact.content)}</pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
