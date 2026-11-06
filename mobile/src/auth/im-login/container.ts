import type { ImContainer, SilentLoginMode } from './types';

export interface ImContainerRule {
  providerKey: ImContainer;
  silent: SilentLoginMode;
  pattern: RegExp;
}

const CONTAINER_RULES: ImContainerRule[] = [
  { providerKey: 'feishu', silent: 'jsapi', pattern: /Feishu|Lark/i },
  { providerKey: 'wecom', silent: 'oauth', pattern: /wxwork/i },
];

export function detectImContainer(userAgent: string): ImContainerRule | null {
  return CONTAINER_RULES.find((item) => item.pattern.test(userAgent || '')) ?? null;
}
