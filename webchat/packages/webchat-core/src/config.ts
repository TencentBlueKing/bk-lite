import type { WebChatConfig } from './types';

const LEGACY_CONFIG_KEYS = [
  'socketUrl',
  'socketPath',
  'enableSSE',
  'reconnectAttempts',
  'reconnectDelay',
] as const;

type LegacyConfigKey = (typeof LEGACY_CONFIG_KEYS)[number];

/** Public configuration after deprecated transport options are normalized. */
export type NormalizedWebChatConfig = Omit<WebChatConfig, LegacyConfigKey> & {
  sseUrl?: string;
};

/**
 * Normalize public configuration before the UI consumes it.
 *
 * JavaScript integrations may still pass unknown top-level keys at runtime.
 * They remain untouched for compatibility, while TypeScript integrations use
 * the named `extensions` namespace.
 */
export function normalizeWebChatConfig(config: WebChatConfig): NormalizedWebChatConfig {
  const normalized = { ...config } as Record<string, unknown>;
  const sseUrl = config.sseUrl ?? config.socketUrl;

  for (const key of LEGACY_CONFIG_KEYS) {
    delete normalized[key];
  }

  if (sseUrl !== undefined) {
    normalized.sseUrl = sseUrl;
  }

  return normalized as NormalizedWebChatConfig;
}
