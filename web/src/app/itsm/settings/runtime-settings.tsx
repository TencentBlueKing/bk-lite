'use client';

import { usePathname } from 'next/navigation';
import { createContext, useContext, useEffect, useRef, useState } from 'react';
import useApiClient from '@/utils/request';

export interface BasicSettings {
  product_name: string;
  tab_title: string;
  attachment_types: string;
  show_process_log: boolean;
  user_display: 'display_name' | 'username';
}

export const defaultBasicSettings: BasicSettings = {
  product_name: 'ITSM',
  tab_title: 'ITSM',
  attachment_types: '',
  show_process_log: true,
  user_display: 'display_name',
};

interface RuntimeSettingsContext {
  settings: BasicSettings;
  updateSettings: (value: BasicSettings) => void;
}

const SettingsContext = createContext<RuntimeSettingsContext>({ settings: defaultBasicSettings, updateSettings: () => {} });

export function ItsmRuntimeSettingsProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { get, isLoading } = useApiClient();
  const [settings, setSettings] = useState(defaultBasicSettings);
  const revision = useRef(0);

  useEffect(() => {
    if (isLoading) return;
    const controller = new AbortController();
    const requested = revision.current;
    void get<BasicSettings>('/itsm/api/settings/basic', {
      params: { runtime: 1 },
      signal: controller.signal,
      suppressErrorNotification: true,
    }).then(value => {
      if (!controller.signal.aborted && revision.current === requested) setSettings({ ...defaultBasicSettings, ...value });
    }).catch(() => {
      if (!controller.signal.aborted && revision.current === requested) setSettings(defaultBasicSettings);
    });
    return () => controller.abort();
  }, [get, isLoading]);

  useEffect(() => {
    const title = settings.tab_title;
    if (title === defaultBasicSettings.tab_title) return;
    const previousTitle = document.title;
    document.title = title;
    return () => {
      if (document.title === title) document.title = previousTitle;
    };
  }, [pathname, settings.tab_title]);

  return <SettingsContext.Provider value={{ settings, updateSettings: value => {
    revision.current += 1;
    setSettings(value);
  } }}>{children}</SettingsContext.Provider>;
}

export const useItsmRuntimeSettings = () => useContext(SettingsContext);
