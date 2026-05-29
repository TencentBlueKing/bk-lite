'use client';

import { useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import { PROFESSIONAL_DASHBOARDS } from '../registry';
import { normalizeDashboardKey } from './index';

export function useResolveObjectId(objectKey: string) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getMonitorObject } = useMonitorApi();
  const resolving = useRef(false);

  useEffect(() => {
    const monitorObjId = searchParams.get('monitorObjId');
    if (monitorObjId || !objectKey || resolving.current) return;

    const normalizedKey = normalizeDashboardKey(objectKey);
    const registryItem = PROFESSIONAL_DASHBOARDS.find(
      (item) => normalizeDashboardKey(item.key) === normalizedKey
    );
    if (!registryItem) return;

    resolving.current = true;

    const resolve = async () => {
      try {
        const objects = await getMonitorObject({ include_invisible: true });
        if (!Array.isArray(objects)) return;

        const matched = objects.find((obj: any) => {
          const objName = normalizeDashboardKey(obj.name);
          const objDisplay = normalizeDashboardKey(obj.display_name);
          return objName === normalizedKey || objDisplay === normalizedKey;
        });

        if (matched) {
          const params = new URLSearchParams(searchParams.toString());
          params.set('monitorObjId', String(matched.id));
          params.set('name', matched.name || registryItem.objectName);
          params.set('monitorObjDisplayName', matched.display_name || registryItem.objectDisplayName || registryItem.objectName);
          if (!params.get('instance_id_keys')) {
            const keys = Array.isArray(matched.instance_id_keys)
              ? matched.instance_id_keys.join(',')
              : 'instance_id';
            params.set('instance_id_keys', keys);
          }
          router.replace(`/monitor/view/dashboard/${objectKey}?${params.toString()}`);
        }
      } finally {
        resolving.current = false;
      }
    };

    resolve();
  }, [objectKey, searchParams]);
}
