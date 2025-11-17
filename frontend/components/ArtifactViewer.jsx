'use client';

import { useState } from 'react';

import StatusBadge from './StatusBadge';

// ----- Formatting helpers -----
function normalizeDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value === 'string') {
    const isoMatch = /^\d{4}-\d{2}-\d{2}T/.test(value);
    if (isoMatch) return new Date(value);
    const legacyMatch = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value);
    if (legacyMatch) {
      return new Date(value.replace(' ', 'T') + 'Z');
    }
    return new Date(value);
  }
  return null;
}

function formatDate(value) {
  const parsed = normalizeDate(value);
  if (!parsed || Number.isNaN(parsed.getTime())) return '—';
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(parsed);
  } catch (error) {
    return value;
  }
}

function parseContent(content) {
  if (typeof content !== 'string') {
    return content;
  }
  try {
    return JSON.parse(content);
  } catch (error) {
    return null;
  }
}

function renderJson(content) {
  const parsed = parseContent(content);
  if (parsed === null) {
    return typeof content === 'string' ? content : JSON.stringify(content, null, 2);
  }
  return JSON.stringify(parsed, null, 2);
}

function formatNumber(value) {
  if (value === null || value === undefined) return '—';
  try {
    return new Intl.NumberFormat().format(value);
  } catch (error) {
    return String(value);
  }
}

function VideoRankings({ data }) {
  const rows = Array.isArray(data) ? data : [];
  if (rows.length === 0) {
    return <p style={{ color: 'var(--color-text-subtle)' }}>No ranked videos captured for this run.</p>;
  }
  return rows.map((group) => {
    const videoRows = Array.isArray(group.videos) ? group.videos : [];
    const maxScore =
      videoRows.length > 0
        ? Math.max(
            ...videoRows
              .map((v) => (typeof v.score === 'number' ? v.score : 0))
              .filter((val) => Number.isFinite(val)),
          )
        : null;
    return (
      <div key={group.skill || 'general'} style={{ marginBottom: '1.25rem' }}>
        <h5 style={{ margin: '0 0 0.5rem 0' }}>{group.skill || 'General skill'}</h5>
        <div className="video-table-wrapper">
          <table className="video-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Score</th>
                <th>Title</th>
                <th>Channel</th>
                <th>Views</th>
                <th>Summary</th>
                <th>Tip</th>
              </tr>
            </thead>
            <tbody>
              {videoRows.map((video) => {
                const rawScore = typeof video.score === 'number' ? video.score : null;
                const normalized =
                  rawScore !== null && maxScore && maxScore > 0 ? (rawScore / maxScore) * 100 : null;
                const summary =
                  (video.analysis && video.analysis.summary) ||
                  video.summary ||
                  (video.analysis && Array.isArray(video.analysis.keyPoints)
                    ? video.analysis.keyPoints.join(', ')
                    : null);
                return (
                  <tr key={`${group.skill}-${video.videoId}-${video.rank}`}>
                    <td>{video.rank ?? '—'}</td>
                    <td>{normalized !== null ? normalized.toFixed(1) : '—'}</td>
                    <td>
                      {video.url ? (
                        <a href={video.url} target="_blank" rel="noreferrer">
                          {video.title || video.videoId || 'Untitled'}
                        </a>
                      ) : (
                        video.title || video.videoId || 'Untitled'
                      )}
                    </td>
                    <td>{video.channelTitle || '—'}</td>
                    <td>{formatNumber(video.viewCount)}</td>
                    <td style={{ maxWidth: '360px' }}>
                      {summary ? summary : <span className="tag muted">Not received</span>}
                    </td>
                    <td style={{ maxWidth: '360px' }}>{video.personalizationTip || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  });
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
                    className={`artifact-content expandable-content${
                      isExpanded ? ' expanded' : ''
                    }${artifact.artifactType === 'video_rankings' ? ' video-artifact' : ''}`}
                    aria-hidden={!isExpanded}
                  >
                    {artifact.artifactType === 'video_rankings' ? (
                      <VideoRankings data={parseContent(artifact.content)} />
                    ) : (
                      <pre>{renderJson(artifact.content)}</pre>
                    )}
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
