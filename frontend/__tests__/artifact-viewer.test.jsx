import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import ArtifactViewer from '../components/ArtifactViewer';

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

const baseSummary = {
  analysisId: 'run-1',
  email: 'user@example.com',
  cvDocId: 'doc',
  status: 'pending',
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
};

const baseDetail = {
  payload: { result: 'ok' },
  lastError: null,
};

test('renders helpful placeholder when no run is selected', () => {
  render(<ArtifactViewer summary={null} detail={null} artifacts={[]} isLoading={false} />);
  expect(screen.getByText(/Select a run/)).toBeInTheDocument();
});

test('payload + artifact accordions expose correct ARIA state', async () => {
  render(
    <ArtifactViewer
      summary={baseSummary}
      detail={baseDetail}
      artifacts={[
        {
          analysisId: 'run-1',
          artifactType: 'cv_text',
          content: '{"text":"hi"}',
          createdAt: new Date().toISOString(),
        },
      ]}
      isLoading={false}
    />,
  );
  const user = userEvent.setup();

  const payloadToggle = screen.getByRole('button', { name: /Expand payload/i });
  expect(payloadToggle).toHaveAttribute('aria-expanded', 'false');
  await user.click(payloadToggle);
  expect(payloadToggle).toHaveAttribute('aria-expanded', 'true');

  const artifactToggle = screen.getByRole('button', { name: /Expand cv_text content/i });
  await user.click(artifactToggle);
  expect(artifactToggle).toHaveAttribute('aria-expanded', 'true');
  await user.click(artifactToggle);
  expect(artifactToggle).toHaveAttribute('aria-expanded', 'false');
});
