import type { ImContainer } from './types';

const CONTAINER_PATTERNS: Array<{ container: ImContainer; pattern: RegExp }> = [
  { container: 'feishu', pattern: /Feishu|Lark/i },
];

export function detectImContainer(userAgent: string): ImContainer | null {
  const matched = CONTAINER_PATTERNS.find((item) => item.pattern.test(userAgent || ''));
  return matched?.container ?? null;
}
