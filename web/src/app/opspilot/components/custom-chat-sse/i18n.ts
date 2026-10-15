/**
 * React 树外的文案翻译。
 *
 * `aguiMessageHandler` 是普通 class、`toolCallRenderer` 输出 HTML 字符串，
 * 都拿不到 hook。宿主（`custom-chat-sse/index.tsx`）在挂载时把当前语言写进来，
 * 这里按 locale 取词；未写入时回退到调用方给的 defaultMessage，行为与迁移前一致。
 */
import { getStoredLocale } from '@/utils/userPreferences';
import en from '@/app/opspilot/locales/en.json';
import zh from '@/app/opspilot/locales/zh.json';

export type OpspilotTranslateValues = Record<string, string | number>;

export type OpspilotTranslate = (
  key: string,
  defaultMessage?: string,
  values?: OpspilotTranslateValues,
) => string;

const flatten = (tree: unknown, prefix = ''): Record<string, string> => {
  if (typeof tree === 'string') {
    return prefix ? { [prefix]: tree } : {};
  }
  if (!tree || typeof tree !== 'object' || Array.isArray(tree)) {
    return {};
  }
  return Object.entries(tree as Record<string, unknown>).reduce<Record<string, string>>(
    (acc, [key, value]) => Object.assign(acc, flatten(value, prefix ? `${prefix}.${key}` : key)),
    {},
  );
};

const CATALOGS: Record<'zh' | 'en', Record<string, string>> = {
  zh: flatten(zh),
  en: flatten(en),
};

let locale: 'zh' | 'en' = 'zh';
let catalog: Record<string, string> = CATALOGS.zh;

const interpolate = (template: string, values?: OpspilotTranslateValues): string => {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = values[key];
    return value == null ? match : String(value);
  });
};

export const setOpspilotModuleLocale = (next: 'zh' | 'en') => {
  locale = next;
  catalog = CATALOGS[next] ?? CATALOGS.zh;
};

/** 供宿主在挂载时同步站点语言。 */
export const syncOpspilotModuleLocale = () => {
  setOpspilotModuleLocale(getStoredLocale() === 'en' ? 'en' : 'zh');
};

export const getOpspilotTranslate = (): OpspilotTranslate => (key, defaultMessage, values) => {
  const message = catalog[key] ?? defaultMessage ?? key;
  return interpolate(message, values);
};

/** 按指定语言取词，不改模块当前语言。无 hook 的纯函数用它保持中文默认。 */
export const translateForLocale = (next: 'zh' | 'en'): OpspilotTranslate => {
  const selected = CATALOGS[next] ?? CATALOGS.zh;
  return (key, defaultMessage, values) => {
    const message = selected[key] ?? defaultMessage ?? key;
    return interpolate(message, values);
  };
};

export const getOpspilotModuleLocale = () => locale;
