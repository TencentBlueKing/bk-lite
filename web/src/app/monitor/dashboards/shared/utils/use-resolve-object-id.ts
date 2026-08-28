'use client';

import { useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import { findProfessionalDashboardMetaByKey, getDashboardObjectMatchKeys } from '../../metadata';
import { normalizeDashboardKey } from './index';
import { buildInstanceDisplayName, encodeInstanceIdValuesParam } from './instance';

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
  params.set('instance_id_values', encodeInstanceIdValuesParam(instance.idValues));
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

    const registryItem = findProfessionalDashboardMetaByKey(objectKey);
    if (!registryItem) return;

    const registryCandidates = getDashboardObjectMatchKeys(registryItem);

    const matchesRouteObject = (obj: {
      name?: string;
      display_name?: string;
    }) => {
      const objName = normalizeDashboardKey(obj.name);
      const objDisplay = normalizeDashboardKey(obj.display_name);
      return (
        registryCandidates.includes(objName) ||
        registryCandidates.includes(objDisplay)
      );
    };

    resolving.current = true;

    const resolve = async () => {
      try {
        const objects = await getMonitorObject({ include_invisible: true });
        if (!Array.isArray(objects)) return;

        const matchedByRoute = objects.find((obj: any) => matchesRouteObject(obj));
        if (!matchedByRoute) return;

        const currentById = monitorObjId
          ? objects.find((obj: any) => String(obj.id) === String(monitorObjId))
          : null;
        const monitorObjMatchesRoute = !!(
          currentById && matchesRouteObject(currentById)
        );

        // 无 monitorObjId，或 URL 残留了其他仪表盘对象的 id 时，纠正到当前路由对象。
        if (!monitorObjMatchesRoute) {
          const params = new URLSearchParams(searchParams.toString());
          params.set('monitorObjId', String(matchedByRoute.id));
          params.set('name', matchedByRoute.name || registryItem.objectName);
          params.set(
            'monitorObjDisplayName',
            matchedByRoute.display_name ||
              registryItem.objectDisplayName ||
              registryItem.objectName
          );
          if (!params.get('instance_id_keys')) {
            const keys = Array.isArray(matchedByRoute.instance_id_keys)
              ? matchedByRoute.instance_id_keys.join(',')
              : 'instance_id';
            params.set('instance_id_keys', keys);
          }

          // 已有 instance 时保留；仅在缺失时补选当前对象首个实例。
          if (!instanceId) {
            const first = await resolveFirstInstance(
              getInstanceList,
              matchedByRoute.id
            );
            if (first) {
              applyInstanceParams(params, first);
            }
          }

          router.replace(
            `/monitor/view/dashboard/${objectKey}?${params.toString()}`
          );
          return;
        }

        if (!instanceId) {
          const first = await resolveFirstInstance(
            getInstanceList,
            matchedByRoute.id
          );
          if (!first) return;

          const params = new URLSearchParams(searchParams.toString());
          applyInstanceParams(params, first);
          router.replace(
            `/monitor/view/dashboard/${objectKey}?${params.toString()}`
          );
        }
      } finally {
        resolving.current = false;
      }
    };

    resolve();
  }, [objectKey, searchParams]);
}
