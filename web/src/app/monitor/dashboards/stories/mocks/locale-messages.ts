// Storybook 无后端，/api/locales 拉不到语言包，导致 t() 回退成原始 key（如
// common.timeSelector.15Minutes）。这里直接打包 base + monitor 的中文语言包并扁平化，
// 让 Storybook 预览的文案与实际环境一致。
import baseZh from '@/locales/zh.json';
import monitorZh from '@/app/monitor/locales/zh.json';

type NestedMessages = { [key: string]: string | NestedMessages };

const flattenMessages = (nested: NestedMessages, prefix = ''): Record<string, string> =>
  Object.keys(nested).reduce((acc, key) => {
    const value = nested[key];
    const prefixedKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      acc[prefixedKey] = value;
    } else {
      Object.assign(acc, flattenMessages(value, prefixedKey));
    }
    return acc;
  }, {} as Record<string, string>);

// 与 /api/locales 一致：base 语言包 + 模块语言包合并后扁平化。
export const STORYBOOK_ZH_MESSAGES: Record<string, string> = {
  ...flattenMessages(baseZh as NestedMessages),
  ...flattenMessages(monitorZh as NestedMessages)
};
