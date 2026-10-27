'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useSession } from 'next-auth/react';
import { useUserInfoContext } from '@/context/userInfo';
import { useHomepageApi } from '@/app/ops-analysis/api/homepage';
import { useEffectiveHomepage } from '@/app/ops-analysis/context/effectiveHomepage';
import type { HomepagePreferenceState } from '@/app/ops-analysis/utils/homepageDirectoryActions';

export type HomepagePreferenceStatus = 'idle' | 'loading' | 'ready' | 'error';

interface HomepagePreferenceValue {
  state: HomepagePreferenceState | null;
  status: HomepagePreferenceStatus;
  /** 首次加载未完成：菜单应用禁用占位，不能当成「未设置」。 */
  isLoading: boolean;
  reload: () => Promise<void>;
  applyPersonal: (data: {
    action: 'set' | 'clear' | 'pin_workbench';
    dashboard_id?: number;
  }) => Promise<HomepagePreferenceState>;
  applyGlobal: (data: {
    action: 'set' | 'restore';
    dashboard_id?: number;
  }) => Promise<HomepagePreferenceState>;
}

const EMPTY_VALUE: HomepagePreferenceValue = {
  state: null,
  status: 'idle',
  isLoading: false,
  reload: async () => {},
  applyPersonal: async () => {
    throw new Error('HomepagePreferenceProvider is missing');
  },
  applyGlobal: async () => {
    throw new Error('HomepagePreferenceProvider is missing');
  },
};

const HomepagePreferenceContext = createContext<HomepagePreferenceValue | null>(null);

export const HomepagePreferenceProvider = ({ children }: { children: React.ReactNode }) => {
  const { status: sessionStatus, data: session } = useSession();
  const { loading: userLoading, selectedGroup, userId, username } = useUserInfoContext();
  const { getState, applyPersonal: postPersonal, applyGlobal: postGlobal } = useHomepageApi();
  const { refresh: refreshEffectiveHomepage } = useEffectiveHomepage();
  const [state, setState] = useState<HomepagePreferenceState | null>(null);
  const [status, setStatus] = useState<HomepagePreferenceStatus>('idle');
  const requestSeq = useRef(0);
  const accountKey = sessionStatus === 'authenticated'
    ? String(userId || username || (session?.user as { id?: string; username?: string } | undefined)?.id || '')
    : '';

  const reload = useCallback(async () => {
    const seq = requestSeq.current + 1;
    requestSeq.current = seq;
    setStatus((prev) => (prev === 'ready' ? prev : 'loading'));
    try {
      const next = await getState({ suppressErrorNotification: true });
      if (seq !== requestSeq.current) {
        return;
      }
      setState(next);
      setStatus('ready');
    } catch {
      if (seq !== requestSeq.current) {
        return;
      }
      setState(null);
      setStatus('error');
    }
  }, [getState]);

  const refreshLogoInBackground = useCallback(() => {
    void refreshEffectiveHomepage().catch(() => {
      // Logo 目标另刷，不阻塞偏好保存后的操作。
    });
  }, [refreshEffectiveHomepage]);

  const applyPersonal = useCallback(async (data: {
    action: 'set' | 'clear' | 'pin_workbench';
    dashboard_id?: number;
  }) => {
    const next = await postPersonal(data);
    requestSeq.current += 1;
    setState(next);
    setStatus('ready');
    refreshLogoInBackground();
    return next;
  }, [postPersonal, refreshLogoInBackground]);

  const applyGlobal = useCallback(async (data: {
    action: 'set' | 'restore';
    dashboard_id?: number;
  }) => {
    const next = await postGlobal(data);
    requestSeq.current += 1;
    setState(next);
    setStatus('ready');
    refreshLogoInBackground();
    return next;
  }, [postGlobal, refreshLogoInBackground]);

  useEffect(() => {
    // 切账号先清空，避免短暂露出上一个账号的配置。
    requestSeq.current += 1;
    setState(null);
    if (sessionStatus !== 'authenticated' || !accountKey) {
      setStatus('idle');
      return;
    }
    setStatus('loading');
  }, [accountKey, sessionStatus]);

  useEffect(() => {
    if (sessionStatus !== 'authenticated' || !accountKey || userLoading) {
      return;
    }
    void reload();
  }, [accountKey, reload, selectedGroup?.id, sessionStatus, userLoading]);

  const value = useMemo<HomepagePreferenceValue>(() => ({
    state,
    status,
    isLoading: status === 'loading' || (status === 'idle' && sessionStatus === 'authenticated'),
    reload,
    applyPersonal,
    applyGlobal,
  }), [applyGlobal, applyPersonal, reload, sessionStatus, state, status]);

  return (
    <HomepagePreferenceContext.Provider value={value}>
      {children}
    </HomepagePreferenceContext.Provider>
  );
};

export const useHomepagePreference = (): HomepagePreferenceValue =>
  useContext(HomepagePreferenceContext) ?? EMPTY_VALUE;
