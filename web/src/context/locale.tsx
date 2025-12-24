'use client';

import { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import { IntlProvider } from 'react-intl';
import { useTranslation } from '@/utils/i18n';
import Spin from '@/components/spin';

const LocaleContext = createContext<{
  locale: string;
  setLocale: (locale: string) => void;
    } | undefined>(undefined);

export const LocaleProvider = ({ children }: { children: ReactNode }) => {
  const [locale, setLocale] = useState('en');
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const savedLocale = localStorage.getItem('locale') || 'en';
    setLocale(savedLocale);
    fetchLocaleMessages(savedLocale);
  }, []);

  const fetchLocaleMessages = async (locale: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(`/api/locales?locale=${locale}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch locale ${locale} from api`);
      }
      const data = await response.json();
      setMessages(data);
    } catch (error) {
      console.error('Failed to load locale messages form api:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const changeLocale = (newLocale: string) => {
    setLocale(newLocale);
    localStorage.setItem('locale', newLocale);
    fetchLocaleMessages(newLocale);
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
