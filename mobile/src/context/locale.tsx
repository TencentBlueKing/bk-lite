'use client';

import {
  createContext,
  useContext,
  useState,
  ReactNode,
  useEffect,
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
  zh: flattenMessages(zhMessages),
  'zh-CN': flattenMessages(zhMessages),
  en: flattenMessages(enMessages),
  'en-US': flattenMessages(enMessages),
};

const LocaleContext = createContext<
  | {
      locale: string;
      setLocale: (locale: string) => void;
        }
        | undefined
        >(undefined);

interface LocaleProviderProps {
  children: ReactNode;
}

export const LocaleProvider = ({ children }: LocaleProviderProps) => {
  const [locale, setLocale] = useState('zh-CN');
  const [messages, setMessages] = useState<Record<string, string>>(
    localeMessages['zh-CN']
  );
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // 从localStorage获取保存的语言设置，默认为中文
    const savedLocale = localStorage.getItem('locale') || 'zh-CN';
    const newMessages = localeMessages[savedLocale] || localeMessages['zh-CN'];

    setLocale(savedLocale);
    setMessages(newMessages);
    setMounted(true);
  }, []);

  const changeLocale = (newLocale: string) => {
    const newMessages = localeMessages[newLocale] || localeMessages['zh-CN'];

    setLocale(newLocale);
    setMessages(newMessages);
    localStorage.setItem('locale', newLocale);
  };

  // 在客户端挂载前使用默认消息避免闪烁
  if (!mounted) {
    return (
      <LocaleContext.Provider value={{ locale, setLocale: changeLocale }}>
        <IntlProvider locale={locale} messages={messages} defaultLocale="zh-CN">
          {children as any}
        </IntlProvider>
      </LocaleContext.Provider>
    );
  }

  return (
    <LocaleContext.Provider value={{ locale, setLocale: changeLocale }}>
      <IntlProvider locale={locale} messages={messages} defaultLocale="zh-CN">
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