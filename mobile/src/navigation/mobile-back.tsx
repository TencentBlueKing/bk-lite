'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { isTauriApp } from '@/utils/tauriFetch';

interface MobileNavigationContextValue {
  back: (fallbackHref: string) => void;
}

interface MobileBackOptions {
  fallbackHref: string;
  onBeforeBack?: () => boolean;
}

const MobileNavigationContext = createContext<MobileNavigationContextValue | null>(null);
const NATIVE_BACK_GESTURE_ENABLED_ROUTES = new Set([
  '/conversations',
  '/search',
  '/workbench/detail',
  '/profile/accountDetails',
]);

function getPathname(href: string) {
  return href.split(/[?#]/, 1)[0] || '/';
}

export function MobileNavigationProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const routeStackRef = useRef<string[]>([]);
  const popStatePendingRef = useRef(false);

  useEffect(() => {
    if (!isTauriApp()) return;

    let active = true;
    const normalizedPathname = pathname.replace(/\/+$/, '') || '/';
    const enabled = NATIVE_BACK_GESTURE_ENABLED_ROUTES.has(normalizedPathname);
    void import('@tauri-apps/api/core')
      .then(({ invoke }) => {
        if (!active) return;
        return invoke('set_back_forward_navigation_gestures', { enabled });
      })
      .catch((error) => {
        console.error('Failed to configure native back gesture:', error);
      });

    return () => {
      active = false;
    };
  }, [pathname]);

  useEffect(() => {
    const markPopState = () => {
      popStatePendingRef.current = true;
    };

    window.addEventListener('popstate', markPopState);
    return () => window.removeEventListener('popstate', markPopState);
  }, []);

  useEffect(() => {
    const stack = routeStackRef.current;
    const previousRoute = stack.at(-2);

    if (popStatePendingRef.current || previousRoute === pathname) {
      const routeIndex = stack.lastIndexOf(pathname);
      routeStackRef.current = routeIndex >= 0
        ? stack.slice(0, routeIndex + 1)
        : [pathname];
    } else if (stack.at(-1) !== pathname) {
      stack.push(pathname);
    }

    popStatePendingRef.current = false;
  }, [pathname]);

  const back = useCallback((fallbackHref: string) => {
    const stack = routeStackRef.current;
    if (stack.length > 1) {
      router.back();
      return;
    }

    const fallbackPathname = getPathname(fallbackHref);
    routeStackRef.current = [fallbackPathname];
    router.replace(fallbackHref);
  }, [router]);

  const value = useMemo(() => ({ back }), [back]);

  return (
    <MobileNavigationContext.Provider value={value}>
      {children}
    </MobileNavigationContext.Provider>
  );
}

export function useMobileBack({ fallbackHref, onBeforeBack }: MobileBackOptions) {
  const navigation = useContext(MobileNavigationContext);
  if (!navigation) {
    throw new Error('useMobileBack must be used within MobileNavigationProvider');
  }

  return useCallback(() => {
    if (onBeforeBack?.()) return;
    navigation.back(fallbackHref);
  }, [fallbackHref, navigation, onBeforeBack]);
}
