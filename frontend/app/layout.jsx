import './globals.css';

export const metadata = {
  title: 'CV-JD Workflow Dashboard',
  description: 'Monitor CV analyses, inspect artifacts, and start new runs.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
