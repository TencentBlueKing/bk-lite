'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { MobileAppLoading } from '@/components/mobile-feedback';
import { useAuth } from '@/context/auth';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { loadAvailabilityFacts } from './adapter';
import {
  MOBILE_MODULE_ORDER,
  MODULE_ROOTS,
  moduleForPath,
  resolveAvailability,
  resolveSafeModule,
  type MobileModuleKey,
  type ResolvedAvailability,
} from './model';

type AvailabilityStatus = 'idle' | 'loading' | 'ready' | 'error';

interface MobileAvailabilityContextValue {
  status: AvailabilityStatus;
  visibleModules: MobileModuleKey[];
  canAccess: (module: MobileModuleKey, operation?: string) => boolean;
  resolveSafeRoot: (preferred?: MobileModuleKey | null) => string;
  rememberModule: (module: MobileModuleKey) => void;
  lastModule: MobileModuleKey | null;
  refresh: () => Promise<void>;
}

const EMPTY_AVAILABILITY: ResolvedAvailability = {
  visibleModules: ['profile'],
  operations: {
    todo: [],
    monitor: [],
    assets: [],
    apps: [],
    profile: [],
  },
};

const MobileAvailabilityContext = createContext<MobileAvailabilityContextValue | null>(null);

interface InFlightRefresh {
  scope: string;
  promise: Promise<void>;
}

function storageKey(username: string, domain: string) {
  return `bk_lite_mobile_last_tab:${encodeURIComponent(domain)}:${encodeURIComponent(username)}`;
}

function readRememberedModule(username: string, domain: string): MobileModuleKey | null {
  if (typeof window === 'undefined') return null;
  const value = window.localStorage.getItem(storageKey(username, domain));
  return MOBILE_MODULE_ORDER.includes(value as MobileModuleKey)
    ? value as MobileModuleKey
    : null;
}

export function MobileAvailabilityProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, userInfo } = useAuth();
  const { locale } = useLocale();
  const username = userInfo?.username ?? '';
  const domain = userInfo?.domain ?? '';
  const refreshScope = isAuthenticated && username
    ? `${locale}\u0000${domain}\u0000${username}`
    : '';
  const [status, setStatus] = useState<AvailabilityStatus>('idle');
  const [availability, setAvailability] = useState(EMPTY_AVAILABILITY);
  const [lastModule, setLastModule] = useState<MobileModuleKey | null>(null);
  const requestIdRef = useRef(0);
  const refreshPromiseRef = useRef<InFlightRefresh | null>(null);

  const refresh = useCallback((): Promise<void> => {
    if (!refreshScope) return Promise.resolve();
    const inFlight = refreshPromiseRef.current;
    if (inFlight?.scope === refreshScope) return inFlight.promise;

    const requestId = ++requestIdRef.current;
    setStatus((current) => current === 'ready' ? current : 'loading');
    const promise = (async () => {
      try {
        const facts = await loadAvailabilityFacts(locale);
        if (requestId !== requestIdRef.current) return;
        setAvailability(resolveAvailability(facts));
        setStatus('ready');
      } catch (error) {
        if (requestId !== requestIdRef.current) return;
        console.error('Failed to resolve Mobile availability:', error);
        setAvailability(EMPTY_AVAILABILITY);
        setStatus('error');
      }
    })();
    const refreshRequest = { scope: refreshScope, promise };
    refreshPromiseRef.current = refreshRequest;
    void promise.finally(() => {
      if (refreshPromiseRef.current === refreshRequest) {
        refreshPromiseRef.current = null;
      }
    });
    return promise;
  }, [locale, refreshScope]);

  useEffect(() => {
    if (!refreshScope) {
      requestIdRef.current += 1;
      refreshPromiseRef.current = null;
      setAvailability(EMPTY_AVAILABILITY);
      setLastModule(null);
      setStatus('idle');
      return;
    }
    setLastModule(readRememberedModule(username, domain));
    void refresh();
  }, [domain, refresh, refreshScope, username]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const refreshOnVisible = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    document.addEventListener('visibilitychange', refreshOnVisible);
    return () => {
      document.removeEventListener('visibilitychange', refreshOnVisible);
    };
  }, [isAuthenticated, refresh]);

  const canAccess = useCallback((module: MobileModuleKey, operation?: string) => {
    if (!availability.visibleModules.includes(module)) return false;
    if (!operation || module === 'profile') return true;
    return availability.operations[module].includes(operation);
  }, [availability]);

  const resolveSafeRoot = useCallback((preferred?: MobileModuleKey | null) => {
    return MODULE_ROOTS[resolveSafeModule(
      availability.visibleModules,
      preferred ?? lastModule,
    )];
  }, [availability.visibleModules, lastModule]);

  const rememberModule = useCallback((module: MobileModuleKey) => {
    if (!refreshScope || !availability.visibleModules.includes(module)) return;
    window.localStorage.setItem(storageKey(username, domain), module);
    setLastModule(module);
  }, [availability.visibleModules, domain, refreshScope, username]);

  const value = useMemo(() => ({
    status,
    visibleModules: availability.visibleModules,
    canAccess,
    resolveSafeRoot,
    rememberModule,
    lastModule,
    refresh,
  }), [
    availability.visibleModules,
    canAccess,
    lastModule,
    refresh,
    rememberModule,
    resolveSafeRoot,
    status,
  ]);

  return (
    <MobileAvailabilityContext.Provider value={value}>
      {children}
    </MobileAvailabilityContext.Provider>
  );
}

export function useMobileAvailability() {
  const context = useContext(MobileAvailabilityContext);
  if (!context) {
    throw new Error('useMobileAvailability must be used within MobileAvailabilityProvider');
  }
  return context;
}

export function MobileAccessGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useTranslation();
  const { status, canAccess, resolveSafeRoot } = useMobileAvailability();
  const routeModule = moduleForPath(pathname);
  const isBusinessRoute = routeModule !== null && routeModule !== 'profile';
  const allowed = routeModule === null || canAccess(routeModule);

  useEffect(() => {
    if (!isBusinessRoute || status === 'loading' || status === 'idle') return;
    if (status === 'error' || !allowed) router.replace(resolveSafeRoot());
  }, [allowed, isBusinessRoute, resolveSafeRoot, router, status]);

  if (isBusinessRoute && (status !== 'ready' || !allowed)) {
    return <MobileAppLoading label={t('common.loading')} />;
  }

  return children;
}
