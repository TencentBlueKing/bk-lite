/**
 * 供仅做类型检查的 tsconfig 使用的 `@webchat/core` 存根。
 *
 * `tests/tsconfig.issue-4637.json` 把 `@webchat/core` 映射到 `types.ts`，
 * 以避免把整个 core（含 React-free 但有副作用的模块）拖进纯类型编译。
 * `imageBudget.ts` 依赖的翻译函数只需签名一致，运行时走 `issue-4637.runtime.json` 的真实 core。
 */
export type { WebChatConfig } from '../packages/webchat-core/src/types';

export type Locale = 'zh' | 'en';
export type TranslateValues = Record<string, string | number>;
export type Translate = (key: string, fallback?: string, values?: TranslateValues) => string;

export declare const translate: Translate;
