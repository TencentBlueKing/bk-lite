import type { Metadata } from 'next';
import './globals.css';
import './layout.css';

export const metadata: Metadata = {
  title: 'WebChat',
  description: 'WebChat - A modern web chat library',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
