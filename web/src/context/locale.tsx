'use client';

import { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import { IntlProvider } from 'react-intl';
import { useTranslation } from '@/utils/i18n';
import Spin from '@/components/spin';
import { getStoredLocale, normalizeLocale, persistLocale } from '@/utils/userPreferences';
import { createLatestRequestGuard } from '@/context/latestRequestGuard';

const LocaleContext = createContext<{
  locale: string;
  setLocale: (locale: string) => void;
    } | undefined>(undefined);

export const LocaleProvider = ({ children }: { children: ReactNode }) => {
  const [locale, setLocale] = useState('en');
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [requestGuard] = useState(createLatestRequestGuard);

  useEffect(() => {
    const savedLocale = getStoredLocale();
    setLocale(savedLocale);
    setIsLoading(true);
    fetchLocaleMessages(savedLocale).finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    return () => requestGuard.invalidate();
  }, [requestGuard]);

  const fetchLocaleMessages = async (locale: string) => {
    const requestId = requestGuard.begin();
    try {
      const response = await fetch(`/api/locales?locale=${locale}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch locale ${locale} from api`);
      }
      const data = await response.json();
      requestGuard.commitIfCurrent(requestId, () => setMessages(data));
    } catch (error) {
      console.error('Failed to load locale messages form api:', error);
    }
  };

  const changeLocale = (newLocale: string) => {
    const normalizedLocale = normalizeLocale(newLocale);
    setLocale(normalizedLocale);
    persistLocale(normalizedLocale);
    fetchLocaleMessages(normalizedLocale);
  };

  return (
    <LocaleContext.Provider value={{ locale, setLocale: changeLocale }}>
      {isLoading ? (
        <Spin></Spin>
      ) : (
        // @ts-expect-error react-intl type incompatibility with React 19
        <IntlProvider locale={locale} messages={messages as any}>
          {children}
        </IntlProvider>
      )}
    </LocaleContext.Provider>
  );
};

export const useLocale = () => {
  const context = useContext(LocaleContext);
  const { t } = useTranslation();

  if (context === undefined) {
    throw new Error(t('common.useLocaleError'));
  }
  return context;
};
