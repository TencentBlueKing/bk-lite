import { createIntl } from 'react-intl';
import { expect, it } from 'vitest';
import { flattenMessages } from '@/utils/dynamicsMerged.mjs';
import en from '../../locales/en.json';
import zh from '../../locales/zh.json';
import { describeCron } from '../scheduleDescription';

function summary(locale: 'zh' | 'en', expression: string) {
  const messages = flattenMessages(locale === 'zh' ? zh : en);
  const intl = createIntl({ locale, messages });
  return describeCron(expression, (id, defaultMessage, values) =>
    intl.formatMessage({ id, defaultMessage }, values));
}

it.each([
  ['0 2 * * *', '每天 02:00'],
  ['15 */2 * * *', '每天从 00:15 起，每 2 小时一次'],
  ['0 */1 * * *', '每小时整点'],
  ['*/10 * * * *', '每 10 分钟一次'],
  ['*/7 * * * *', '每小时从整点起，每 7 分钟一次'],
  ['30 9 * * 1-5', '每周一至周五 09:30'],
  ['30 9 * * 0', '每周日 09:30'],
  ['0 8 1 * *', '每月 1 日 08:00'],
  ['30 9 1 * 1-5', '自定义周期'],
  ['30 9 * 6 1-5', '自定义周期'],
  ['60 9 * * *', '自定义周期'],
  ['', '-'],
])('%s displays %s', (expression, expected) => {
  expect(summary('zh', expression)).toBe(expected);
});

it('formats English weekday schedules with their time', () => {
  expect(summary('en', '30 9 * * 1-5')).toBe('Monday to Friday at 09:30');
});
