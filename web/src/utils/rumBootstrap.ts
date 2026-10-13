export type RumBootstrapConfig = {
  app: string;
  endpoint: string;
  apiKey: string;
  environment: string;
};

const browserEnv = (): Record<string, string | undefined> => ({
  // Next only inlines a direct `process.env.NEXT_PUBLIC_*` access.
  NEXT_PUBLIC_RUM_APP: process.env.NEXT_PUBLIC_RUM_APP,
  NEXT_PUBLIC_RUM_ENDPOINT: process.env.NEXT_PUBLIC_RUM_ENDPOINT,
  NEXT_PUBLIC_RUM_API_KEY: process.env.NEXT_PUBLIC_RUM_API_KEY,
  NEXT_PUBLIC_RUM_ENVIRONMENT: process.env.NEXT_PUBLIC_RUM_ENVIRONMENT,
});

export const readRumBootstrapConfig = (
  env: Record<string, string | undefined> = browserEnv(),
): RumBootstrapConfig | null => {
  const app = env.NEXT_PUBLIC_RUM_APP?.trim() ?? '';
  const endpoint = (env.NEXT_PUBLIC_RUM_ENDPOINT?.trim() ?? '').replace(/\/+$/, '');
  const apiKey = env.NEXT_PUBLIC_RUM_API_KEY?.trim() ?? '';
  if (!app || !endpoint || !apiKey) {
    return null;
  }
  return {
    app,
    endpoint,
    apiKey,
    environment: env.NEXT_PUBLIC_RUM_ENVIRONMENT?.trim() || 'development',
  };
};
