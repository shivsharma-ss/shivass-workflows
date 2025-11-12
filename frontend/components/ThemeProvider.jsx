'use client';

import { createContext, startTransition, useContext, useEffect, useMemo, useState } from 'react';

// Persist user choice so the dashboard theme stays sticky between sessions.
const STORAGE_KEY = 'dashboard-theme';

const ThemeContext = createContext(undefined);

function getStoredTheme() {
  if (typeof window === 'undefined') {
    return null;
  }
  const value = window.localStorage.getItem(STORAGE_KEY);
  return value === 'dark' || value === 'light' ? value : null;
}

function getPreferredTheme() {
  if (typeof window === 'undefined') {
    return 'light';
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    if (typeof document === 'undefined') {
      return 'light';
    }
    const attr = document.documentElement.dataset.theme;
    return attr === 'dark' ? 'dark' : 'light';
  });
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // Hydrate from localStorage or fall back to the OS preference.
    const initial = getStoredTheme() ?? getPreferredTheme();
    startTransition(() => {
      setTheme(initial);
      setIsReady(true);
    });
  }, []);

  useEffect(() => {
    if (typeof document === 'undefined') {
      return;
    }
    // Write the chosen theme to the DOM + storage so SSR and future loads match.
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme === 'dark' ? 'dark' : 'light';
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch (error) {
      // Ignore storage errors (e.g., Safari private mode).
    }
  }, [theme]);

  // Expose stable context value so consumers avoid unnecessary re-renders.
  const value = useMemo(
    () => ({
      theme,
      isReady,
      setTheme,
      toggleTheme: () => setTheme((prev) => (prev === 'dark' ? 'light' : 'dark')),
    }),
    [theme, isReady],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (ctx === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return ctx;
}
