import { render, type RenderOptions } from '@testing-library/react';
import { App } from 'antd';
import type { ReactElement } from 'react';
import { IntlProvider } from 'react-intl';
import en from './locales/en.json';
import zh from './locales/zh.json';

interface LocaleMessages {
  [key: string]: string | LocaleMessages;
}

function flattenMessages(messages: LocaleMessages, prefix = ''): Record<string, string> {
  return Object.fromEntries(Object.entries(messages).flatMap(([key, value]) => {
    const id = prefix ? `${prefix}.${key}` : key;
    return typeof value === 'string' ? [[id, value]] : Object.entries(flattenMessages(value, id));
  }));
}

const messages = { en: flattenMessages(en), zh: flattenMessages(zh) };

export function renderItsm(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'> & { locale?: 'zh' | 'en' }) {
  const { locale = 'zh', ...renderOptions } = options ?? {};
  return render(ui, {
    ...renderOptions,
    wrapper: ({ children }) => <IntlProvider locale={locale} messages={messages[locale]}><App>{children}</App></IntlProvider>,
  });
}
