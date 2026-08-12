'use client';

export interface NatsChannelExtension {
  buildInitialConfig: () => Record<string, unknown>;
  mergeConfig: (config: Record<string, unknown>) => Record<string, unknown>;
  normalizeConfig: (config: Record<string, unknown>) => Record<string, unknown>;
  getVisibleConfigKeys: (mode: unknown) => string[];
  getFieldDefinition: (key: string) => Record<string, unknown> | undefined;
  testChannel: (payload: Record<string, unknown>) => Promise<void>;
}

const useCommunityNatsChannelExtension = (): NatsChannelExtension | null => null;

const loadNatsChannelExtension = () => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('@/app/system-manager/(enterprise)/hooks/useNatsNotificationExtension');
    return mod.useNatsNotificationExtension || useCommunityNatsChannelExtension;
  } catch {
    return useCommunityNatsChannelExtension;
  }
};

export const useNatsChannelExtension = loadNatsChannelExtension();
