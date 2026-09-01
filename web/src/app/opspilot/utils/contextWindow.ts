export type ContextWindowUnit = 'K' | 'M';

export const DEFAULT_CONTEXT_WINDOW_VALUE = 200;
export const DEFAULT_CONTEXT_WINDOW_UNIT: ContextWindowUnit = 'K';
export const MIN_CONTEXT_WINDOW_TOKENS = 8_000;
export const MAX_CONTEXT_WINDOW_TOKENS = 2_000_000;

export function tokensFromWindowInput(value: number, unit: ContextWindowUnit): number {
  const amount = Math.trunc(Number(value));
  if (!Number.isFinite(amount) || amount <= 0) {
    return 0;
  }
  return unit === 'M' ? amount * 1_000_000 : amount * 1_000;
}

export function windowInputFromTokens(tokens?: number | null): { value: number; unit: ContextWindowUnit } {
  const amount = Math.trunc(Number(tokens));
  if (!Number.isFinite(amount) || amount <= 0) {
    return { value: DEFAULT_CONTEXT_WINDOW_VALUE, unit: DEFAULT_CONTEXT_WINDOW_UNIT };
  }
  if (amount >= 1_000_000 && amount % 1_000_000 === 0) {
    return { value: amount / 1_000_000, unit: 'M' };
  }
  if (amount % 1_000 === 0) {
    return { value: amount / 1_000, unit: 'K' };
  }
  return { value: DEFAULT_CONTEXT_WINDOW_VALUE, unit: DEFAULT_CONTEXT_WINDOW_UNIT };
}

export function isContextWindowTokensInRange(tokens: number): boolean {
  return tokens >= MIN_CONTEXT_WINDOW_TOKENS && tokens <= MAX_CONTEXT_WINDOW_TOKENS;
}
