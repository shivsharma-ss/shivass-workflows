'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { createAnalysis, fetchAnalyses, fetchAnalysisStatus, fetchArtifacts } from '../lib/api';
import AnalysisForm from './AnalysisForm';
import ArtifactViewer from './ArtifactViewer';
import RunHistoryTable from './RunHistoryTable';

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
  const [lastUpdated, setLastUpdated] = useState(null);

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

    const controller = new AbortController();
    const { signal } = controller;
    setDetailLoading(true);
    Promise.all([
      fetchAnalysisStatus(selectedId, signal),
      fetchArtifacts(selectedId, signal),
    ])
      .then(([statusPayload, artifactPayload]) => {
        setDetail(statusPayload);
        setArtifacts(Array.isArray(artifactPayload) ? artifactPayload : []);
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error('Failed to load run details', error);
        }
      })
      .finally(() => {
        setDetailLoading(false);
      });

    return () => controller.abort();
  }, [selectedId]);

  const handleSubmit = useCallback(
    async (formValues) => {
      setIsSubmitting(true);
      setFeedback(null);
      try {
        await createAnalysis(formValues);
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
        return false;
      } finally {
        setIsSubmitting(false);
      }
    },
    [loadAnalyses],
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', paddingBottom: '3rem' }}>
      <header>
        <h1>Workflow control center</h1>
        <p style={{ color: '#475569', fontSize: '1.05rem', maxWidth: '720px' }}>
          Launch new CV-versus-job-description analyses, observe live run status, and drill into artifacts
          produced by the orchestrator. The dashboard polls automatically every 15 seconds.
        </p>
      </header>

      <AnalysisForm onSubmit={handleSubmit} isSubmitting={isSubmitting} feedback={feedback} />

      <div className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Total runs</h3>
          <p style={{ fontSize: '2.5rem', margin: '0.25rem 0', fontWeight: 700 }}>{statusBreakdown.total}</p>
          <p style={{ color: '#64748b', margin: 0 }}>All time analyses stored in SQLite.</p>
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Active pipelines</h3>
          <p style={{ fontSize: '2.5rem', margin: '0.25rem 0', fontWeight: 700 }}>
            {statusBreakdown.pending + statusBreakdown.running + statusBreakdown.awaiting_approval}
          </p>
          <p style={{ color: '#64748b', margin: 0 }}>Pending, running, or awaiting approval.</p>
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Successful runs</h3>
          <p style={{ fontSize: '2.5rem', margin: '0.25rem 0', fontWeight: 700 }}>{statusBreakdown.completed}</p>
          <p style={{ color: '#64748b', margin: 0 }}>Ready-to-send recommendation packs.</p>
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Failures</h3>
          <p style={{ fontSize: '2.5rem', margin: '0.25rem 0', fontWeight: 700 }}>{statusBreakdown.failed}</p>
          <p style={{ color: '#64748b', margin: 0 }}>Investigate payloads and retry.</p>
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
