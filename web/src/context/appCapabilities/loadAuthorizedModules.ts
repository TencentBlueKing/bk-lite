import { listAuthorizedCapabilityApps } from './access';
import {
  APP_CAPABILITY_LOADERS,
  APP_CAPABILITY_NAMES,
  type AppCapabilityName,
} from './catalog';
import { loadAuthorizedCapability } from './load';
import type { LoadedCapabilitySlots } from './slots';
import type { AppCapabilityModule } from './types';

export async function loadAuthorizedCapabilityModules(
  clientData: Array<{ name?: string | null }> | null | undefined
): Promise<LoadedCapabilitySlots[]> {
  const apps = listAuthorizedCapabilityApps(
    (clientData || [])
      .map((item) => item.name)
      .filter((name): name is string => Boolean(name)),
    APP_CAPABILITY_NAMES
  );

  const modules: Array<LoadedCapabilitySlots | null> = await Promise.all(
    apps.map(async (appName) => {
      const loader = APP_CAPABILITY_LOADERS[appName as AppCapabilityName];
      if (!loader) return null;
      const mod = await loadAuthorizedCapability(appName, {
        authorized: true,
        load: loader as () => Promise<AppCapabilityModule>,
      });
      if (!mod) return null;
      return {
        appName,
        slots: (mod as AppCapabilityModule).slots,
      };
    })
  );

  return modules.filter((item): item is LoadedCapabilitySlots => item !== null);
}
