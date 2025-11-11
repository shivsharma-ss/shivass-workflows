'use client';

import { useState } from 'react';

const INITIAL_FORM = {
  email: '',
  cvDocId: '',
  jobDescription: '',
  jobDescriptionUrl: '',
};

export default function AnalysisForm({ onSubmit, isSubmitting, feedback }) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [validationError, setValidationError] = useState(null);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!form.jobDescription && !form.jobDescriptionUrl) {
      setValidationError('Provide either a job description or a job URL.');
      return;
    }

    setValidationError(null);
    const success = await onSubmit(form);
    if (success) {
      setForm(INITIAL_FORM);
    }
  };

  return (
    <div className="card">
      <h2>Kick off a new analysis</h2>
      <p style={{ color: '#475569', marginTop: '0.25rem' }}>
        Submit the candidate&apos;s CV and target role to launch the LangGraph workflow.
      </p>
      <form onSubmit={handleSubmit} style={{ marginTop: '1.5rem', display: 'grid', gap: '1.25rem' }}>
        <div>
          <label htmlFor="email">Notification email *</label>
          <input
            id="email"
            name="email"
            type="email"
            placeholder="you@example.com"
            value={form.email}
            required
            onChange={handleChange}
            autoComplete="email"
          />
        </div>
        <div>
          <label htmlFor="cvDocId">CV Google Doc ID *</label>
          <input
            id="cvDocId"
            name="cvDocId"
            type="text"
            placeholder="Document ID from the Google Docs URL"
            value={form.cvDocId}
            required
            onChange={handleChange}
          />
          <small style={{ color: '#64748b' }}>Example: https://docs.google.com/document/d/<strong>DOC_ID</strong>/edit</small>
        </div>
        <div className="form-row">
          <div>
            <label htmlFor="jobDescription">Job description</label>
            <textarea
              id="jobDescription"
              name="jobDescription"
              rows={6}
              placeholder="Paste the job description text..."
              value={form.jobDescription}
              onChange={handleChange}
            />
          </div>
          <div>
            <label htmlFor="jobDescriptionUrl">Job description URL</label>
            <input
              id="jobDescriptionUrl"
              name="jobDescriptionUrl"
              type="url"
              placeholder="https://company.com/job-posting"
              value={form.jobDescriptionUrl}
              onChange={handleChange}
            />
          </div>
        </div>
        <div className="form-actions">
          <button type="submit" className="primary-button" disabled={isSubmitting}>
            {isSubmitting ? 'Submitting...' : 'Start workflow'}
          </button>
          <span className="refresh-indicator">A detailed report will be emailed when the run completes.</span>
        </div>
        {validationError && <div className="alert error">{validationError}</div>}
        {feedback?.message && <div className={`alert ${feedback.variant}`}>{feedback.message}</div>}
      </form>
    </div>
  );
}
