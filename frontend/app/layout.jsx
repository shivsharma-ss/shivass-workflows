import Script from 'next/script';

import { ThemeProvider } from '../components/ThemeProvider';
import './globals.css';

export const metadata = {
  title: 'CV-JD Workflow Dashboard',
  description: 'Monitor CV analyses, inspect artifacts, and start new runs.',
};

const THEME_BOOTSTRAP = `(() => {
  try {
    const stored = window.localStorage.getItem('dashboard-theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = stored === 'dark' || stored === 'light' ? stored : prefersDark ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme === 'dark' ? 'dark' : 'light';
  } catch (error) {
    document.documentElement.dataset.theme = 'light';
    document.documentElement.style.colorScheme = 'light';
  }
})();`;

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Script
          id="theme-bootstrap"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }}
        />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
