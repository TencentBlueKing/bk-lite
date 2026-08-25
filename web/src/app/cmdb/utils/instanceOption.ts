import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';

export interface CmdbInstanceOption<T extends Record<string, unknown> = Record<string, unknown>> {
  label: string;
  value: string;
  origin: T;
}

const readText = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number'
    ? String(value).trim()
    : '';

export const toCmdbInstanceOptions = <T extends Record<string, unknown>>(
  instances: readonly T[]
): CmdbInstanceOption<T>[] =>
  instances.flatMap((instance) => {
    const instUuid = resolveCmdbInstUuid(instance.inst_uuid);
    if (!instUuid) return [];

    const label =
      readText(instance.inst_name) ||
      readText(instance.name) ||
      readText(instance.ip_addr) ||
      readText(instance.subnet_address) ||
      readText(instance.management_address) ||
      instUuid;

    return [{ label, value: instUuid, origin: instance }];
  });
