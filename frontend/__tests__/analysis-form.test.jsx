import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import AnalysisForm from '../components/AnalysisForm';
import {
  buildInitialForm,
  clampBoost,
  cloneDefaultChannels,
  computeChipAccent,
  formatBoost,
  generateChannelId,
} from '../components/analysisFormHelpers';

let originalRandomUUID;

beforeAll(() => {
  originalRandomUUID = globalThis.crypto?.randomUUID;
  let counter = 0;
  const randomUUID = () => `test-channel-${counter += 1}`;
  if (!globalThis.crypto) {
    Object.defineProperty(globalThis, 'crypto', {
      value: { randomUUID },
    });
  } else {
    globalThis.crypto.randomUUID = randomUUID;
  }
});

afterAll(() => {
  if (originalRandomUUID) {
    globalThis.crypto.randomUUID = originalRandomUUID;
  }
});

beforeEach(() => {
  const originalError = console.error;
  vi.spyOn(console, 'error').mockImplementation((message, ...args) => {
    if (typeof message === 'string' && message.includes('not wrapped in act')) {
      return;
    }
    originalError(message, ...args);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

const renderForm = (props = {}) =>
  render(
    <AnalysisForm
      onSubmit={props.onSubmit || (() => true)}
      isSubmitting={props.isSubmitting || false}
      feedback={props.feedback || null}
    />,
  );

test('normalizes IDs and channels before submission', async () => {
  const onSubmit = vi.fn().mockResolvedValue(true);
  render(<AnalysisForm onSubmit={onSubmit} isSubmitting={false} feedback={null} />);
  const user = userEvent.setup();

  await user.type(screen.getByLabelText(/Notification email/i), 'candidate@example.com');
  const docField = screen.getByLabelText(/CV Google Doc ID/i);
  await user.clear(docField);
  fireEvent.change(docField, {
    target: {
      value: 'https://docs.google.com/document/d/abc123456789012345678901234567890123456789/edit',
      name: 'cvDocId',
    },
  });
  await waitFor(() => expect(docField).toHaveValue('abc123456789012345678901234567890123456789'));
  await user.type(
    screen.getByLabelText('Job description', { selector: 'textarea' }),
    'Ship reliable workflows',
  );

  await user.click(screen.getByRole('button', { name: /Start workflow/i }));

  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  const payload = onSubmit.mock.calls[0][0];
  expect(payload.cvDocId).toBe('abc123456789012345678901234567890123456789');
  expect(payload.preferredYoutubeChannels).not.toHaveLength(0);
  expect(screen.getByLabelText(/Notification email/i)).toHaveValue('');
});

test('shows validation message when job description inputs are empty', async () => {
  renderForm({ onSubmit: vi.fn() });
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/Notification email/i), 'candidate@example.com');
  await user.type(screen.getByLabelText(/CV Google Doc ID/i), 'doc123');

  await user.click(screen.getByRole('button', { name: /Start workflow/i }));

  expect(screen.getByRole('alert')).toHaveTextContent('Provide either a job description or a job URL.');
});

test('allows editing channel boosts with accessible controls', async () => {
  renderForm();
  const user = userEvent.setup();
  const chip = screen.getByRole('button', { name: /freeCodeCamp\.org/i });
  await user.click(chip);

  const slider = screen.getByLabelText('Boost multiplier');
  fireEvent.change(slider, { target: { value: '1.75' } });
  expect(slider).toHaveValue('1.75');

  const nameInput = screen.getByLabelText('Channel name');
  await user.clear(nameInput);
  await user.type(nameInput, 'Curated Creator');
  expect(nameInput).toHaveValue('Curated Creator');

  await user.click(screen.getByRole('button', { name: /Done/i }));
  expect(chip).toHaveAttribute('aria-expanded', 'false');
});

test('restores default channels after clearing the list', async () => {
  renderForm();
  const user = userEvent.setup();
  const removeChannelByName = async (name) => {
    const chip = screen.getByRole('button', { name: new RegExp(name, 'i') });
    await user.click(chip);
    await user.click(screen.getByRole('button', { name: /^Remove$/i }));
  };

  await removeChannelByName('freeCodeCamp');
  await removeChannelByName('Tech With Tim');
  await removeChannelByName('IBM Technology');

  expect(screen.getByText(/No preferred channels yet/i)).toBeInTheDocument();
  const restoreButton = screen.getByRole('button', { name: /Restore defaults/i });
  await user.click(restoreButton);
  expect(screen.queryByText(/No preferred channels yet/i)).not.toBeInTheDocument();
});

test('clicking outside the channel editor closes the popover', async () => {
  renderForm();
  const user = userEvent.setup();
  const chip = screen.getByRole('button', { name: /freeCodeCamp\.org/i });
  await user.click(chip);
  expect(chip).toHaveAttribute('aria-expanded', 'true');

  fireEvent.mouseDown(document.body);
  await waitFor(() => expect(chip).toHaveAttribute('aria-expanded', 'false'));
});

test('pressing Escape closes whichever channel is active', async () => {
  renderForm();
  const user = userEvent.setup();
  const chip = screen.getByRole('button', { name: /freeCodeCamp\.org/i });
  await user.click(chip);
  expect(chip).toHaveAttribute('aria-expanded', 'true');

  fireEvent.keyDown(window, { key: 'Escape' });
  await waitFor(() => expect(chip).toHaveAttribute('aria-expanded', 'false'));
});

test('surface submit errors when onSubmit rejects', async () => {
  const onSubmit = vi.fn().mockRejectedValue(new Error('Boom'));
  const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  render(<AnalysisForm onSubmit={onSubmit} isSubmitting={false} feedback={null} />);
  const user = userEvent.setup();

  await user.type(screen.getByLabelText(/Notification email/i), 'candidate@example.com');
  await user.type(screen.getByLabelText(/CV Google Doc ID/i), 'doc123456789012345678901234567890123456789');
  await user.type(screen.getByLabelText('Job description', { selector: 'textarea' }), 'Details');

  await user.click(screen.getByRole('button', { name: /Start workflow/i }));

  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  expect(screen.getByRole('alert')).toHaveTextContent('Boom');
  consoleSpy.mockRestore();
});

describe('analysis form helper utilities', () => {
  const originalCrypto = globalThis.crypto;

  afterEach(() => {
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: originalCrypto,
    });
  });

  test('clampBoost enforces numeric ranges and defaults', () => {
    expect(clampBoost('not-a-number')).toBe(1.1);
    expect(clampBoost(0.25)).toBe(0.5);
    expect(clampBoost(3)).toBe(2);
    expect(clampBoost(1.75)).toBe(1.75);
  });

  test('formatBoost displays multipliers without trailing zeros', () => {
    expect(formatBoost(1)).toBe('1×');
    expect(formatBoost(1.234)).toBe('1.23×');
  });

  test('generateChannelId prefers crypto.randomUUID with fallback', () => {
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: {
        randomUUID: () => 'test-id',
      },
    });
    expect(generateChannelId()).toBe('test-id');

    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: {},
    });
    const fallback = generateChannelId();
    expect(fallback).toMatch(/^channel-/);
  });

  test('cloneDefaultChannels returns deep copies with normalized boosts', () => {
    const clone = cloneDefaultChannels();
    expect(Array.isArray(clone)).toBe(true);
    expect(clone[0]).toHaveProperty('id');
    clone[0].name = 'mutated';
    const nextClone = cloneDefaultChannels();
    expect(nextClone[0].name).not.toBe('mutated');
  });

  test('computeChipAccent produces gradient definitions', () => {
    const { chipStyle, avatarStyle } = computeChipAccent('Example Channel');
    expect(chipStyle.background).toContain('linear-gradient');
    expect(avatarStyle.color).toBe('#fff');
  });

  test('buildInitialForm seeds default state', () => {
    const form = buildInitialForm();
    expect(form).toMatchObject({
      email: '',
      cvDocId: '',
      jobDescription: '',
      jobDescriptionUrl: '',
    });
    expect(form.preferredYoutubeChannels.length).toBeGreaterThan(0);
  });
});
