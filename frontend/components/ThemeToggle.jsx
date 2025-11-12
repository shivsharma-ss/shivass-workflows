'use client';

import { useTheme } from './ThemeProvider';

export default function ThemeToggle() {
  const { theme, toggleTheme, isReady } = useTheme();
  const isDark = theme === 'dark';
  const toggleLabel = isDark ? 'Switch to light mode' : 'Switch to dark mode';
  const stateLabel = isDark ? 'Dark mode enabled' : 'Light mode enabled';
  const tooltipText = isDark ? 'Rise and shine!' : 'Lights out!';

  // Keep accessibility labels and visuals in sync with the resolved theme.
  return (
    <button
      type="button"
      className={`theme-toggle${!isReady ? ' theme-toggle--loading' : ''}`}
      onClick={toggleTheme}
      aria-pressed={isDark}
      aria-label={toggleLabel}
      title={tooltipText}
      disabled={!isReady}
    >
      <span className="sr-only" aria-live="polite">
        {isReady ? stateLabel : 'Detecting theme preference'}
      </span>
      <span className="theme-toggle__track" aria-hidden="true">
        <span className="theme-toggle__stars" />
        <span className="theme-toggle__orb">
          <span className="theme-toggle__sun" />
          <span className="theme-toggle__moon">
            <span />
            <span />
            <span />
          </span>
        </span>
      </span>
    </button>
  );
}
