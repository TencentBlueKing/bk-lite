import en from '@/locales/en.json';
import zh from '@/locales/zh.json';

export interface AppDisplaySource {
  name?: string;
  display_name?: string;
  description?: string;
  is_build_in?: boolean;
}

type TranslateFn = (id: string, defaultMessage?: string) => string;

const BUILTIN_APP_IDS = new Set([
  'monitor',
  'log',
  'cmdb',
  'alarm',
  'job',
  'ops-analysis',
  'ops-console',
  'system-manager',
  'node',
  'opspilot',
  'mlops',
  'patch',
  'apm',
  'playground',
]);

const isBuiltinApp = (app: AppDisplaySource): app is AppDisplaySource & { name: string } =>
  Boolean(app.name) && app.is_build_in !== false && BUILTIN_APP_IDS.has(app.name as string);

const TAG_KEY_BY_ALIAS = (() => {
  const map = new Map<string, string>();
  const register = (tags?: Record<string, string>) => {
    if (!tags) {
      return;
    }
    for (const [id, value] of Object.entries(tags)) {
      map.set(id, id);
      map.set(`tag.${id}`, id);
      if (value) {
        map.set(value, id);
      }
    }
  };
  register((en as { tag?: Record<string, string> }).tag);
  register((zh as { tag?: Record<string, string> }).tag);
  return map;
})();

export const resolveAppDisplayName = (
  app: AppDisplaySource,
  t: TranslateFn
): string => {
  const fallback = (app.display_name || app.name || '').trim();
  if (!isBuiltinApp(app)) {
    return fallback;
  }
  return t(`apps.${app.name}`, fallback);
};

export const resolveAppDescription = (
  app: AppDisplaySource,
  t: TranslateFn
): string => {
  const fallback = (app.description || '').trim();
  if (!isBuiltinApp(app)) {
    return fallback;
  }
  return t(`app.${app.name}`, fallback);
};

export const resolveAppTag = (tag: string, t: TranslateFn): string => {
  const key = TAG_KEY_BY_ALIAS.get(tag);
  if (!key) {
    return tag;
  }
  return t(`tag.${key}`, tag);
};
