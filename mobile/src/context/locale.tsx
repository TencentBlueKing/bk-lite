'use client';

import {
  createContext,
  useContext,
  useState,
  ReactNode,
  useEffect,
  useCallback,
} from 'react';
import { IntlProvider } from 'react-intl';
import zhMessages from '@/locales/zh.json';
import enMessages from '@/locales/en.json';

// 预加载的语言包 - 扁平化结构
const flattenMessages = (
  nestedMessages: any,
  prefix = ''
): Record<string, string> => {
  return Object.keys(nestedMessages).reduce(
    (messages: Record<string, string>, key) => {
      const value = nestedMessages[key];
      const prefixedKey = prefix ? `${prefix}.${key}` : key;

      if (typeof value === 'string') {
        messages[prefixedKey] = value;
      } else {
        Object.assign(messages, flattenMessages(value, prefixedKey));
      }

      return messages;
    },
    {}
  );
};

const localeMessages: Record<string, Record<string, string>> = {
  'zh-Hans': flattenMessages(zhMessages),
  'zh': flattenMessages(zhMessages),
  'zh-CN': flattenMessages(zhMessages),
  'en': flattenMessages(enMessages),
  'en-US': flattenMessages(enMessages),
};

// 默认语言
const DEFAULT_LOCALE = 'zh-Hans';

interface LocaleContextType {
  locale: string;
  setLocale: (locale: string) => void;
}

const LocaleContext = createContext<LocaleContextType | undefined>(undefined);

interface LocaleProviderProps {
  children: ReactNode;
}

export const LocaleProvider = ({ children }: LocaleProviderProps) => {
  const [locale, setLocaleState] = useState(DEFAULT_LOCALE);
  const [messages, setMessages] = useState<Record<string, string>>(
    localeMessages[DEFAULT_LOCALE]
  );
  const [mounted, setMounted] = useState(false);

  // 设置语言
  const setLocale = useCallback((newLocale: string) => {
    const newMessages = localeMessages[newLocale] || localeMessages[DEFAULT_LOCALE];

    setLocaleState(newLocale);
    setMessages(newMessages);
  }, []);

  useEffect(() => {
    // 初始化时从安全存储获取用户信息中的 locale
    const initLocale = async () => {
      try {
        const { getUserInfoFromStorage, initSecureStorage } = await import('@/utils/secureStorage');
        await initSecureStorage();
        const userInfo = await getUserInfoFromStorage();

        if (userInfo?.locale) {
          setLocale(userInfo.locale);
        }
      } catch (error) {
        console.error('Failed to load locale from user info:', error);
      } finally {
        setMounted(true);
      }
    };

    initLocale();
  }, [setLocale]);

  // 在客户端挂载前使用默认消息避免闪烁
  if (!mounted) {
    return (
      <LocaleContext.Provider value={{ locale, setLocale }}>
        <IntlProvider locale={locale} messages={messages} defaultLocale={DEFAULT_LOCALE}>
          {children as any}
        </IntlProvider>
      </LocaleContext.Provider>
    );
  }

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      <IntlProvider locale={locale} messages={messages} defaultLocale={DEFAULT_LOCALE}>
        {children as any}
      </IntlProvider>
    </LocaleContext.Provider>
  );
};

export const useLocale = () => {
  const context = useContext(LocaleContext);

  if (context === undefined) {
    throw new Error('useLocale must be used within a LocaleProvider');
  }
  return context;
};