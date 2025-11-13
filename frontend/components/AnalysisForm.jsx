'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import { DEFAULT_CHANNEL_SUGGESTIONS } from '../lib/defaultChannels';
import { extractDocIdFromGoogleDocUrl } from '../lib/googleDocs';
import {
  clampBoost,
  formatBoost,
  generateChannelId,
  cloneDefaultChannels,
  computeChipAccent,
  buildInitialForm,
} from './analysisFormHelpers';

export default function AnalysisForm({ onSubmit, isSubmitting, feedback }) {
  const [form, setForm] = useState(() => buildInitialForm());
  const [activeChannelId, setActiveChannelId] = useState(null);
  const [validationError, setValidationError] = useState(null);
  const [submitError, setSubmitError] = useState(null);
  const channelSectionRef = useRef(null);

  // ----- Derived form bits -----
  const preferredChannels = useMemo(
    () => form.preferredYoutubeChannels || [],
    [form.preferredYoutubeChannels],
  );

  const normalizedDefaultNames = useMemo(
    () => DEFAULT_CHANNEL_SUGGESTIONS.map((channel) => channel.name.trim().toLowerCase()),
    [],
  );

  const hasMissingDefaults = useMemo(() => {
    if (!preferredChannels.length) {
      return normalizedDefaultNames.length > 0;
    }
    const current = new Set(
      preferredChannels.map((channel) => (channel.name || '').trim().toLowerCase()),
    );
    return normalizedDefaultNames.some((name) => !current.has(name));
  }, [preferredChannels, normalizedDefaultNames]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    const nextValue = name === 'cvDocId' ? extractDocIdFromGoogleDocUrl(value) : value;
    setForm((prev) => ({ ...prev, [name]: nextValue }));
  };

  useEffect(() => {
    // Collapse the channel editor when clicking anywhere outside the chip grid.
    if (!activeChannelId) {
      return undefined;
    }
    const handleClickOutside = (event) => {
      if (!channelSectionRef.current) {
        return;
      }
      if (!channelSectionRef.current.contains(event.target)) {
        setActiveChannelId(null);
      }
    };
    window.addEventListener('mousedown', handleClickOutside);
    return () => window.removeEventListener('mousedown', handleClickOutside);
  }, [activeChannelId]);

  useEffect(() => {
    // Keyboard escape also closes whichever chip is focused.
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setActiveChannelId(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // ----- Event handlers -----
  const handleChannelFieldChange = (channelId, field, value) => {
    setForm((prev) => {
      const nextChannels = (prev.preferredYoutubeChannels || []).map((channel) => {
        if (channel.id !== channelId) {
          return channel;
        }
        if (field === 'boost') {
          return { ...channel, boost: clampBoost(value) };
        }
        return { ...channel, [field]: value };
      });
      return { ...prev, preferredYoutubeChannels: nextChannels };
    });
  };

  const handleChipToggle = (channelId) => {
    setActiveChannelId((current) => (current === channelId ? null : channelId));
  };

  const handleAddChannel = () => {
    const newChannel = {
      id: generateChannelId(),
      name: '',
      boost: 1.1,
      isDefault: false,
    };
    setForm((prev) => ({
      ...prev,
      preferredYoutubeChannels: [...(prev.preferredYoutubeChannels || []), newChannel],
    }));
    setActiveChannelId(newChannel.id);
  };

  const handleRemoveChannel = (channelId) => {
    setForm((prev) => ({
      ...prev,
      preferredYoutubeChannels: (prev.preferredYoutubeChannels || []).filter(
        (channel) => channel.id !== channelId,
      ),
    }));
    setActiveChannelId((current) => (current === channelId ? null : current));
  };

  const handleRestoreDefaults = () => {
    setForm((prev) => ({
      ...prev,
      preferredYoutubeChannels: cloneDefaultChannels(),
    }));
    setActiveChannelId(null);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!form.jobDescription && !form.jobDescriptionUrl) {
      setValidationError('Provide either a job description or a job URL.');
      return;
    }

    setValidationError(null);
    setSubmitError(null);
    // Normalize IDs + channels so the API receives clean payloads even if the user pasted URLs everywhere.
    const parsedCvDocId = extractDocIdFromGoogleDocUrl(form.cvDocId);
    const sanitizedChannels = preferredChannels
      .map((channel) => ({
        name: channel?.name?.trim(),
        boost: clampBoost(channel?.boost ?? 1.1),
      }))
      .filter((channel) => Boolean(channel.name));
    try {
      const success = await onSubmit({
        ...form,
        cvDocId: parsedCvDocId,
        preferredYoutubeChannels: sanitizedChannels,
      });
      if (success) {
        setForm(buildInitialForm());
        setActiveChannelId(null);
      }
      return success;
    } catch (error) {
      console.error('Failed to submit analysis form', error);
      setSubmitError(error?.message || 'Unable to start the workflow. Please try again.');
      return false;
    }
  };

  // ----- Render -----
  return (
    <div className="card">
      <h2>Kick off a new analysis</h2>
      <p style={{ color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
        Submit the candidate&apos;s CV and target role to launch the LangGraph workflow.
      </p>
      <form
        onSubmit={handleSubmit}
        style={{ marginTop: '1.5rem', display: 'grid', gap: '1.25rem' }}
      >
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
          <small style={{ color: 'var(--color-text-subtle)' }}>
            Paste the full Google Docs link and we&apos;ll grab the document ID automatically.
          </small>
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
        <div className="channel-section" ref={channelSectionRef}>
          <label>Preferred YouTube channels</label>
          <p className="channel-helper">
            Prioritize trusted creators so the ranking leans toward their tutorials. Boosts are
            gentle multipliers between 0.5× and 2×.
          </p>
          {preferredChannels.length === 0 ? (
            <div className="channel-empty">
              <p>No preferred channels yet.</p>
              <small>You can add any creator you trust and adjust the boost multiplier.</small>
            </div>
          ) : (
            <div className="channel-grid">
              {preferredChannels.map((channel) => {
                const isActive = activeChannelId === channel.id;
                const chipId = `channel-chip-${channel.id}`;
                const popoverId = `channel-popover-${channel.id}`;
                const accents = computeChipAccent(channel.name);
                const initial =
                  (channel.name && channel.name.trim().charAt(0).toUpperCase()) ||
                  channel.id.charAt(channel.id.length - 1).toUpperCase();
                return (
                  <div key={channel.id} className="channel-chip-wrapper">
                    <button
                      type="button"
                      className={`channel-chip${isActive ? ' channel-chip--active' : ''}`}
                      aria-expanded={isActive}
                      aria-controls={popoverId}
                      id={chipId}
                      style={accents.chipStyle}
                      onClick={() => handleChipToggle(channel.id)}
                    >
                      <span
                        className="channel-chip__avatar"
                        style={accents.avatarStyle}
                        aria-hidden="true"
                      >
                        {initial}
                      </span>
                      <span className="channel-chip__name">
                        {channel.name || 'Unnamed channel'}
                      </span>
                      <span className="channel-chip__boost">{formatBoost(channel.boost)}</span>
                      {channel.isDefault && <span className="channel-chip__badge">Suggested</span>}
                    </button>
                    {isActive && (
                      <div
                        className="channel-popover"
                        id={popoverId}
                        role="dialog"
                        aria-labelledby={chipId}
                      >
                        <div className="channel-popover__field">
                          <label htmlFor={`channel-name-${channel.id}`}>Channel name</label>
                          <input
                            id={`channel-name-${channel.id}`}
                            type="text"
                            placeholder="Creator name"
                            value={channel.name || ''}
                            onChange={(event) =>
                              handleChannelFieldChange(channel.id, 'name', event.target.value)
                            }
                          />
                        </div>
                        <div className="channel-popover__field">
                          <div className="channel-popover__label-row">
                            <label htmlFor={`channel-boost-${channel.id}`}>Boost multiplier</label>
                            <span className="channel-popover__boost-value">
                              {formatBoost(channel.boost)}
                            </span>
                          </div>
                          <input
                            id={`channel-boost-${channel.id}`}
                            type="range"
                            min={0.5}
                            max={2}
                            step={0.05}
                            value={channel.boost ?? 1.1}
                            className="channel-popover__slider"
                            onChange={(event) =>
                              handleChannelFieldChange(channel.id, 'boost', event.target.value)
                            }
                          />
                        </div>
                        <div className="channel-popover__actions">
                          <button
                            type="button"
                            className="ghost-button channel-popover__remove"
                            onClick={() => handleRemoveChannel(channel.id)}
                          >
                            Remove
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => setActiveChannelId(null)}
                          >
                            Done
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div className="channel-actions">
            <button type="button" className="secondary-button" onClick={handleAddChannel}>
              {preferredChannels.length === 0 ? '+ Add preferred channel' : 'Add another channel'}
            </button>
            {hasMissingDefaults && (
              <button type="button" className="ghost-button" onClick={handleRestoreDefaults}>
                Restore defaults
              </button>
            )}
          </div>
        </div>
        <div className="form-actions">
          <button type="submit" className="primary-button" disabled={isSubmitting}>
            {isSubmitting ? 'Submitting...' : 'Start workflow'}
          </button>
          <span className="refresh-indicator">
            A detailed report will be emailed when the run completes.
          </span>
        </div>
        {validationError && (
          <div className="alert error" role="alert" aria-live="assertive">
            {validationError}
          </div>
        )}
        {submitError && (
          <div className="alert error" role="alert" aria-live="assertive">
            {submitError}
          </div>
        )}
        {feedback?.message && (
          <div className={`alert ${feedback.variant}`} role="status" aria-live="polite">
            {feedback.message}
          </div>
        )}
      </form>
    </div>
  );
}
