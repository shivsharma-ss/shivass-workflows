'use client';

import { useState } from 'react';

import StatusBadge from './StatusBadge';

// ----- Formatting helpers -----
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
  const [expandedArtifact, setExpandedArtifact] = useState(null);
  const [payloadExpanded, setPayloadExpanded] = useState(false);
  const payloadContentId = 'workflow-payload-content';

  const toggleArtifact = (key) => {
    setExpandedArtifact((prev) => (prev === key ? null : key));
  };

  const togglePayload = () => {
    setPayloadExpanded((prev) => !prev);
  };

  // Guard state so empty selections still render helpful guidance.
  if (!summary) {
    return (
      <div className="card" style={{ minHeight: '320px' }}>
        <h2>Run details</h2>
        <p style={{ color: 'var(--color-text-subtle)' }}>
          Select a run from the history to inspect payloads and artifacts.
        </p>
      </div>
    );
  }

  // Main detail surface holds metadata, payload, and artifacts.
  return (
    <div className="card" style={{ minHeight: '320px' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '1rem',
        }}
      >
        <div>
          <h2 style={{ marginBottom: '0.25rem' }}>Run details</h2>
          <p style={{ color: 'var(--color-text-muted)', margin: 0 }}>
            Inspect structured payloads saved during execution.
          </p>
        </div>
        <StatusBadge status={summary.status} />
      </div>

      <div className="status-grid" style={{ marginTop: '1.5rem' }}>
        <div className="status-card">
          <strong>Analysis ID</strong>
          <div className="status-value" style={{ fontFamily: 'monospace' }}>
            {summary.analysisId}
          </div>
        </div>
        <div className="status-card">
          <strong>Email</strong>
          <div className="status-value">{summary.email}</div>
        </div>
        <div className="status-card">
          <strong>CV doc ID</strong>
          <div className="status-value" style={{ fontFamily: 'monospace' }}>
            {summary.cvDocId}
          </div>
        </div>
        <div className="status-card">
          <strong>Created</strong>
          <div className="status-value">{formatDate(summary.createdAt)}</div>
        </div>
        <div className="status-card">
          <strong>Updated</strong>
          <div className="status-value">{formatDate(summary.updatedAt)}</div>
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
          <>
            <div
              id={payloadContentId}
              className={`expandable-content${payloadExpanded ? ' expanded' : ''}`}
              aria-hidden={!payloadExpanded}
            >
              <pre>{renderJson(detail.payload || {})}</pre>
            </div>
            <button
              type="button"
              className="expand-toggle-button"
              onClick={togglePayload}
              aria-label={payloadExpanded ? 'Collapse payload' : 'Expand payload'}
              aria-expanded={payloadExpanded}
              aria-controls={payloadContentId}
            >
              {payloadExpanded ? 'Collapse' : 'Expand to read more'}
            </button>
          </>
        ) : (
          <p style={{ color: 'var(--color-text-subtle)' }}>
            {isLoading ? 'Loading payload...' : 'No payload recorded yet.'}
          </p>
        )}
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <h3 style={{ marginBottom: '0.75rem' }}>Artifacts</h3>
        {isLoading && artifacts.length === 0 ? (
          <p style={{ color: 'var(--color-text-subtle)' }}>Loading artifacts...</p>
        ) : artifacts.length === 0 ? (
          <p style={{ color: 'var(--color-text-subtle)' }}>
            No artifacts have been persisted for this run.
          </p>
        ) : (
          <div className="artifact-list">
            {artifacts.map((artifact, index) => {
              const artifactKey =
                artifact.id ??
                (artifact.analysisId
                  ? `${artifact.analysisId}-${artifact.artifactType}-${artifact.createdAt}`
                  : null) ??
                `${artifact.artifactType}-${artifact.createdAt}-${index}`;
              const isExpanded = expandedArtifact === artifactKey;
              const safeKey = String(artifactKey).replace(/[^a-zA-Z0-9_-]/g, '') || index;
              const contentId = `artifact-content-${safeKey}`;
              return (
                <div key={artifactKey} className="artifact-item">
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'baseline',
                      gap: '0.75rem',
                    }}
                  >
                    <h4 style={{ marginBottom: 3 }}>{artifact.artifactType}</h4>
                    <span className="refresh-indicator">{formatDate(artifact.createdAt)}</span>
                  </div>
                  <div
                    id={contentId}
                    className={`artifact-content expandable-content${isExpanded ? ' expanded' : ''}`}
                    aria-hidden={!isExpanded}
                  >
                    <pre>{renderJson(artifact.content)}</pre>
                  </div>
                  <button
                    type="button"
                    className="expand-toggle-button"
                    onClick={() => toggleArtifact(artifactKey)}
                    aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${artifact.artifactType} content`}
                    aria-expanded={isExpanded}
                    aria-controls={contentId}
                  >
                    {isExpanded ? 'Collapse' : 'Expand to read more'}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
