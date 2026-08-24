'use client';

import { useCallback } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  MODULE_OBJECT_QUERY_PARAM,
  VIEW_OBJECT_QUERY_PARAM,
  buildMonitorObjectUrl,
  rememberMonitorObjectId,
  shouldSyncMonitorObjectUrl
} from '@/app/monitor/utils/monitorObjectQuery';

export const useMonitorObjectQuery = (
  paramName:
    | typeof VIEW_OBJECT_QUERY_PARAM
    | typeof MODULE_OBJECT_QUERY_PARAM = MODULE_OBJECT_QUERY_PARAM
) => {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const syncObjectId = useCallback(
    (objectId: unknown) => {
      rememberMonitorObjectId(objectId);
      if (!shouldSyncMonitorObjectUrl(searchParams, objectId, paramName)) {
        return;
      }
      router.replace(
        buildMonitorObjectUrl(pathname || '', searchParams, objectId, paramName),
        { scroll: false }
      );
    },
    [paramName, pathname, router, searchParams]
  );

  return { syncObjectId, searchParams };
};
