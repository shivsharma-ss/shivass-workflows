import React from 'react';
import { act } from 'react-dom/test-utils';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import ThemeToggle from '../components/ThemeToggle';
import { ThemeProvider } from '../components/ThemeProvider';

const TestHarness = () => (
  <ThemeProvider>
    <ThemeToggle />
  </ThemeProvider>
);

const renderHarness = async () => {
  await act(async () => {
    render(<TestHarness />);
  });
};

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
});

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.dataset.theme = '';
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

test('hydrates from stored theme preference', async () => {
  window.localStorage.setItem('dashboard-theme', 'dark');
  await renderHarness();
  const toggle = await screen.findByRole('button', { name: /Switch to light mode/i });
  await waitFor(() => expect(toggle).not.toBeDisabled());
  expect(toggle).toHaveAttribute('aria-pressed', 'true');
});

test('toggle updates DOM dataset and persists theme', async () => {
  await renderHarness();
  const user = userEvent.setup();
  const toggle = await screen.findByRole('button', { name: /Switch to dark mode/i });
  await waitFor(() => expect(toggle).not.toBeDisabled());
  await user.click(toggle);

  await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
  expect(window.localStorage.getItem('dashboard-theme')).toBe('dark');
});
