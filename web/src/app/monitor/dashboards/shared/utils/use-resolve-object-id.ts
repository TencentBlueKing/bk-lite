'use client';

import { useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import { PROFESSIONAL_DASHBOARDS } from '../../registry';
import { normalizeDashboardKey } from './index';
import { buildInstanceDisplayName } from './instance';

async function resolveFirstInstance(
  getInstanceList: ReturnType<typeof useMonitorApi>['getInstanceList'],
  objectId: string | number
) {
  try {
    const data = await getInstanceList(objectId, { page_size: 1 });
    const first = data?.results?.[0];
    if (!first?.instance_id) return null;
    const value = String(first.instance_id);
    const label = buildInstanceDisplayName(first);
    const idValues = Array.isArray(first.instance_id_values) && first.instance_id_values.length
      ? first.instance_id_values
      : [value];
    return { value, label, idValues };
  } catch {
    return null;
  }
}

function applyInstanceParams(
  params: URLSearchParams,
  instance: { value: string; label: string; idValues: string[] }
) {
  params.set('instance_id', instance.value);
  params.set('instance_name', instance.label);
  params.set('instance_id_values', instance.idValues.join(','));
}

export function useResolveObjectId(objectKey: string) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getMonitorObject, getInstanceList } = useMonitorApi();
  const resolving = useRef(false);

  useEffect(() => {
    const monitorObjId = searchParams.get('monitorObjId');
    const instanceId = searchParams.get('instance_id');

    if (resolving.current || !objectKey) return;

    if (!monitorObjId) {
      const normalizedKey = normalizeDashboardKey(objectKey);
      const registryItem = PROFESSIONAL_DASHBOARDS.find(
        (item) =>
          [item.key, ...(item.aliases || []), item.objectName, item.objectDisplayName]
            .filter(Boolean)
            .map((value) => normalizeDashboardKey(value))
            .includes(normalizedKey)
      );
      if (!registryItem) return;
      const registryCandidates = [registryItem.key, ...(registryItem.aliases || []), registryItem.objectName, registryItem.objectDisplayName]
        .filter(Boolean)
        .map((value) => normalizeDashboardKey(value));

      resolving.current = true;

      const resolve = async () => {
        try {
          const objects = await getMonitorObject({ include_invisible: true });
          if (!Array.isArray(objects)) return;

          const matched = objects.find((obj: any) => {
            const objName = normalizeDashboardKey(obj.name);
            const objDisplay = normalizeDashboardKey(obj.display_name);
            return registryCandidates.includes(objName) || registryCandidates.includes(objDisplay);
          });

          if (!matched) return;

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

          if (!instanceId) {
            const first = await resolveFirstInstance(getInstanceList, matched.id);
            if (first) {
              applyInstanceParams(params, first);
            }
          }

          router.replace(`/monitor/view/dashboard/${objectKey}?${params.toString()}`);
        } finally {
          resolving.current = false;
        }
      };

      resolve();
      return;
    }

    if (monitorObjId && !instanceId) {
      resolving.current = true;

      const autoSelect = async () => {
        try {
          const first = await resolveFirstInstance(getInstanceList, monitorObjId);
          if (!first) return;

          const params = new URLSearchParams(searchParams.toString());
          applyInstanceParams(params, first);
          router.replace(`/monitor/view/dashboard/${objectKey}?${params.toString()}`);
        } finally {
          resolving.current = false;
        }
      };

      autoSelect();
    }
  }, [objectKey, searchParams]);
}
