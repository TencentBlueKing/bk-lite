import type { ReactNode } from 'react';

export const metadata = {
  referrer: 'no-referrer' as const,
  robots: {
    index: false,
    follow: false,
  },
};

export default function ShareLayout({ children }: { children: ReactNode }) {
  return children;
}
