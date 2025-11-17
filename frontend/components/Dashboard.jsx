'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { createAnalysis, fetchAnalyses, fetchAnalysisStatus, fetchArtifacts } from '../lib/api';
import AnalysisForm from './AnalysisForm';
import ArtifactViewer from './ArtifactViewer';
import RunHistoryTable from './RunHistoryTable';
import ThemeToggle from './ThemeToggle';

// Dashboard polling cadence so the entire page can reason about it in one place.
const AUTO_REFRESH_MS = 15000;

export default function Dashboard() {
  const [analyses, setAnalyses] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [artifacts, setArtifacts] = useState([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [queuedRunId, setQueuedRunId] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  // ----- Derived dashboard state -----
  const selectedSummary = useMemo(
    () => analyses.find((item) => item.analysisId === selectedId) || null,
    [analyses, selectedId],
  );

  const statusBreakdown = useMemo(() => {
    const counts = {
      total: analyses.length,
      pending: 0,
      running: 0,
      awaiting_approval: 0,
      completed: 0,
      failed: 0,
    };
    analyses.forEach((run) => {
      counts[run.status] = (counts[run.status] || 0) + 1;
    });
    return counts;
  }, [analyses]);

  // ----- Data loading -----
  const loadAnalyses = useCallback(async () => {
    setRunsLoading(true);
    try {
      const items = await fetchAnalyses(100);
      setAnalyses(items);
      setLastUpdated(new Date().toISOString());
      if (items.length === 0) {
        setSelectedId(null);
      } else if (!items.some((item) => item.analysisId === selectedId)) {
        setSelectedId(items[0].analysisId);
      }
    } catch (error) {
      console.error('Failed to load analyses', error);
    } finally {
      setRunsLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    // Kick off an initial fetch and keep polling while the dashboard is mounted.
    loadAnalyses();
    const interval = setInterval(loadAnalyses, AUTO_REFRESH_MS);
    return () => clearInterval(interval);
  }, [loadAnalyses]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setArtifacts([]);
      return;
    }

    // Fetch status + artifacts in parallel, cancelling stale requests on selection change.
    const controller = new AbortController();
    const { signal } = controller;
    let isActive = true;
    setDetailLoading(true);
    Promise.all([fetchAnalysisStatus(selectedId, signal), fetchArtifacts(selectedId, signal)])
      .then(([statusPayload, artifactPayload]) => {
        if (!isActive) return;
        setDetail(statusPayload);
        setArtifacts(Array.isArray(artifactPayload) ? artifactPayload : []);
      })
      .catch((error) => {
        if (!isActive) return;
        if (error.name !== 'AbortError') {
          console.error('Failed to load run details', error);
        }
      })
      .finally(() => {
        if (!isActive) return;
        setDetailLoading(false);
      });

    return () => {
      isActive = false;
      controller.abort();
    };
  }, [selectedId]);

  // ----- Actions -----
  const handleSubmit = useCallback(
    async (formValues) => {
      setIsSubmitting(true);
      setFeedback(null);
      try {
        const response = await createAnalysis(formValues);
        setQueuedRunId(response?.analysisId || null);
        setFeedback({
          message: 'Workflow queued successfully. Expect the review email shortly.',
          variant: 'success',
        });
        await loadAnalyses();
        return true;
      } catch (error) {
        setFeedback({
          message: error.message || 'Unable to start analysis. Please try again.',
          variant: 'error',
        });
        setQueuedRunId(null);
        return false;
      } finally {
        setIsSubmitting(false);
      }
    },
    [loadAnalyses],
  );

  useEffect(() => {
    if (!queuedRunId || !feedback || feedback.variant !== 'success') {
      return;
    }
    const queuedSummary = analyses.find((run) => run.analysisId === queuedRunId);
    if (queuedSummary && queuedSummary.status !== 'pending') {
      setFeedback(null);
      setQueuedRunId(null);
    }
  }, [analyses, queuedRunId, feedback]);

  // ----- Render -----
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', paddingBottom: '3rem' }}>
      <header className="page-header">
        <div>
          <h1>Workflow control center</h1>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '1.05rem', maxWidth: '720px' }}>
            Launch new CV-versus-job-description analyses, observe live run status, and drill into
            artifacts produced by the orchestrator. The dashboard polls automatically every 15
            seconds.
          </p>
        </div>
        <ThemeToggle />
      </header>

      <AnalysisForm onSubmit={handleSubmit} isSubmitting={isSubmitting} feedback={feedback} />

      <div className="grid">
        <div className="summarycard">
          <h3 style={{ marginTop: 0 }}>Total runs</h3>
          <p style={{ fontSize: '2.5rem', margin: '0.25rem 0', fontWeight: 700 }}>
            {statusBreakdown.total}
          </p>
          <p style={{ color: 'var(--color-text-subtle)', margin: 0 }}>
            All time analyses stored in SQLite.
          </p>
        </div>
        <div className="summarycard">
          <h3 style={{ marginTop: 0 }}>Active pipelines</h3>
          <p style={{ fontSize: '2.5rem', margin: '0.25rem 0', fontWeight: 700 }}>
            {statusBreakdown.pending + statusBreakdown.running + statusBreakdown.awaiting_approval}
          </p>
          <p style={{ color: 'var(--color-text-subtle)', margin: 0 }}>
            Pending, running, or awaiting approval.
          </p>
        </div>
      </div>
      <div className="grid">
        <div className="summarycard">
          <h3 style={{ marginTop: 0 }}>Successful runs</h3>
          <p style={{ fontSize: '2.5rem', margin: '0.25rem 0', fontWeight: 700 }}>
            {statusBreakdown.completed}
          </p>
          <p style={{ color: 'var(--color-text-subtle)', margin: 0 }}>
            Ready-to-send recommendation packs.
          </p>
        </div>
        <div className="summarycard">
          <h3 style={{ marginTop: 0 }}>Failures</h3>
          <p style={{ fontSize: '2.5rem', margin: '0.25rem 0', fontWeight: 700 }}>
            {statusBreakdown.failed}
          </p>
          <p style={{ color: 'var(--color-text-subtle)', margin: 0 }}>
            Investigate payloads and retry.
          </p>
        </div>
      </div>

      <RunHistoryTable
        analyses={analyses}
        selectedId={selectedId}
        onSelect={setSelectedId}
        isLoading={runsLoading}
        onRefresh={loadAnalyses}
        lastUpdated={lastUpdated}
      />

      <ArtifactViewer
        summary={selectedSummary}
        detail={detail}
        artifacts={artifacts}
        isLoading={detailLoading}
      />
    </div>
  );
}
