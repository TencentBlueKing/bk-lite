import {
  GroupedUnitItem,
  GroupedUnitList,
  UnitListItem,
  UserItem,
} from '@/app/monitor/types';
import { getMonitorUnitSelectLabel } from '@/app/monitor/components/monitor-shared/unit-label';

interface LoadState {
  requestLoading: boolean;
  userInfoLoading: boolean;
  selectedGroupId?: string | number | null;
}

interface LoadMonitorCommonDataParams {
  getAllUsers: () => Promise<UserItem[]>;
  getUnitList: () => Promise<UnitListItem[]>;
}

export interface MonitorCommonData {
  users: UserItem[];
  units: UnitListItem[];
  groupedUnits: GroupedUnitList[];
}

// 会话级缓存:同组织下只拉一次 user_all / unit/list
const commonDataCache = new Map<string, MonitorCommonData>();
const commonDataInflight = new Map<string, Promise<MonitorCommonData>>();

export const shouldLoadMonitorCommonData = ({
  requestLoading,
  userInfoLoading,
  selectedGroupId,
}: LoadState) => {
  return !requestLoading && !userInfoLoading && !!selectedGroupId;
};

export const buildGroupedUnitList = (units: UnitListItem[]): GroupedUnitList[] => {
  const groupedByCategory = units.reduce<Record<string, Array<UnitListItem & GroupedUnitItem>>>(
    (acc, item) => {
      if (!acc[item.category]) {
        acc[item.category] = [];
      }
      acc[item.category].push({
        ...item,
        label: getMonitorUnitSelectLabel(item),
        value: item.unit_id,
        unit: item.display_unit,
      });
      return acc;
    },
    {}
  );

  return Object.entries(groupedByCategory).map(([category, children]) => ({
    label: category,
    children,
  })) as GroupedUnitList[];
};

export const loadMonitorCommonData = async ({
  getAllUsers,
  getUnitList,
  cacheKey,
}: LoadMonitorCommonDataParams & { cacheKey?: string }): Promise<MonitorCommonData> => {
  const key = cacheKey || '__default__';
  const cached = commonDataCache.get(key);
  if (cached) {
    return cached;
  }

  const inflight = commonDataInflight.get(key);
  if (inflight) {
    return inflight;
  }

  const request = (async () => {
    const [usersResult, unitsResult] = await Promise.allSettled([
      getAllUsers(),
      getUnitList(),
    ]);
    const users =
      usersResult.status === 'fulfilled' && Array.isArray(usersResult.value)
        ? usersResult.value
        : [];
    const units =
      unitsResult.status === 'fulfilled' && Array.isArray(unitsResult.value)
        ? unitsResult.value
        : [];

    const data: MonitorCommonData = {
      users,
      units,
      groupedUnits: buildGroupedUnitList(units),
    };
    commonDataCache.set(key, data);
    return data;
  })();

  commonDataInflight.set(key, request);
  try {
    return await request;
  } finally {
    commonDataInflight.delete(key);
  }
};

/** 测试或切换组织后清空会话缓存 */
export const clearMonitorCommonDataCache = () => {
  commonDataCache.clear();
  commonDataInflight.clear();
};
