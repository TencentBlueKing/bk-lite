'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { applyScreenAwareHref } from './screenMode';

export const useScreenAwareRouter = () => {
  const router = useRouter();
  const searchParams = useSearchParams();

  const navigate = useCallback(
    (method: 'push' | 'replace', href: string, options?: { scroll?: boolean }) => {
      const nextHref = applyScreenAwareHref(href, searchParams);
      if (options) {
        router[method](nextHref, options);
        return;
      }
      router[method](nextHref);
    },
    [router, searchParams],
  );

  const push = useCallback(
    (href: string, options?: { scroll?: boolean }) => navigate('push', href, options),
    [navigate],
  );

  const replace = useCallback(
    (href: string, options?: { scroll?: boolean }) => navigate('replace', href, options),
    [navigate],
  );

  return useMemo(
    () => ({
      ...router,
      push,
      replace,
    }),
    [push, replace, router],
  );
};
