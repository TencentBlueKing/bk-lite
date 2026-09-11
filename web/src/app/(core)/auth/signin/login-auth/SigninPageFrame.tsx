'use client';

import type { ReactNode } from 'react';
import { usePortalBranding } from '@/hooks/usePortalBranding';
import SigninLanguageToggle from './SigninLanguageToggle';

interface SigninPageFrameProps {
  title: string;
  children: ReactNode;
}

export default function SigninPageFrame({ title, children }: SigninPageFrameProps) {
  const { logoUrl, portalName } = usePortalBranding();

  return (
    <div className="grid min-h-screen w-[calc(100%+2rem)] -m-4 overflow-y-auto bg-[var(--color-bg-1)] lg:grid-cols-[minmax(0,1fr)_clamp(420px,26vw,460px)]">
      <aside
        aria-hidden="true"
        className="hidden min-h-screen bg-cover bg-center bg-no-repeat lg:block"
        style={{ backgroundImage: "url('/system-login-bg-plain.jpg')" }}
      />
      <main className="relative flex min-h-screen flex-col bg-[var(--color-bg-1)] px-5 py-5 sm:px-8 sm:py-8 lg:px-7 lg:py-8 lg:shadow-[-10px_0_24px_var(--color-fill-4)]">
        <header className="flex items-center justify-between gap-3">
          <h1
            className="min-w-0 truncate text-lg font-semibold text-(--color-text-1)"
            title={portalName}
          >
            {portalName}
          </h1>
          <div className="shrink-0">
            <SigninLanguageToggle />
          </div>
        </header>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-[360px] lg:-translate-y-7">
            <div className="mb-4 text-center">
              <div className="mb-1 flex justify-center">
                <img src={logoUrl} alt="" className="h-14 w-auto object-contain" />
              </div>
              <h2 className="text-2xl font-semibold text-(--color-text-1)">{title}</h2>
            </div>
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
