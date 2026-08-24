import { toCmdbInstanceOptions } from '@/app/cmdb/utils/instanceOption';
import type { CmdbInstanceOption } from '@/app/cmdb/utils/instanceOption';

export type IpTaskSubnetOption = CmdbInstanceOption & { prefixlen?: number };

export const toIpTaskSubnetOptions = (
  instances: readonly Record<string, unknown>[]
): IpTaskSubnetOption[] =>
  toCmdbInstanceOptions(instances).map((option) => {
    const prefixlen = Number(
      option.origin.prefixlen ?? option.origin.prefix_len
    );
    return {
      ...option,
      prefixlen: Number.isFinite(prefixlen) ? prefixlen : undefined,
    };
  });
