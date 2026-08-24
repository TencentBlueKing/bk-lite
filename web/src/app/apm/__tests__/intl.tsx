import type { ReactElement } from 'react';
import { IntlProvider } from 'react-intl';
import { render, type RenderOptions } from '@testing-library/react';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import commonZh from '@/locales/zh.json';
import apmZh from '@/app/apm/locales/zh.json';

interface NestedMessages {
  [key: string]: string | NestedMessages;
}

export function flattenMessages(nested: NestedMessages, prefix = ''): Record<string, string> {
  return Object.keys(nested).reduce((messages: Record<string, string>, key: string) => {
    const value = nested[key];
    const prefixedKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      messages[prefixedKey] = value;
    } else {
      Object.assign(messages, flattenMessages(value, prefixedKey));
    }
    return messages;
  }, {});
}

export const apmZhMessages = {
  ...flattenMessages(commonZh as NestedMessages),
  ...flattenMessages(apmZh as NestedMessages),
};

export function renderWithApmIntl(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  dayjs.locale('zh-cn');
  return render(ui, {
    ...options,
    wrapper: ({ children }) => (
      <IntlProvider locale="zh" messages={apmZhMessages} onError={() => undefined}>
        {children}
      </IntlProvider>
    ),
  });
}
