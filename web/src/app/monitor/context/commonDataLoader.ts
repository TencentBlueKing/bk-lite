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

interface CachedCommonPartial {
  users?: UserItem[];
  units?: UnitListItem[];
  usersReady: boolean;
  unitsReady: boolean;
}

// 会话级缓存:同组织下成功的 user_all / unit/list 只拉一次；失败部分可重试
const commonDataCache = new Map<string, CachedCommonPartial>();
const commonDataInflight = new Map<string, Promise<MonitorCommonData>>();

const toMonitorCommonData = (partial: CachedCommonPartial): MonitorCommonData => {
  const users = partial.usersReady && Array.isArray(partial.users) ? partial.users : [];
  const units = partial.unitsReady && Array.isArray(partial.units) ? partial.units : [];
  return {
    users,
    units,
    groupedUnits: buildGroupedUnitList(units),
  };
};

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
  if (cached?.usersReady && cached.unitsReady) {
    return toMonitorCommonData(cached);
  }

  const inflight = commonDataInflight.get(key);
  if (inflight) {
    return inflight;
  }

  const request = (async () => {
    const previous = commonDataCache.get(key) ?? { usersReady: false, unitsReady: false };
    const needUsers = !previous.usersReady;
    const needUnits = !previous.unitsReady;
    const [usersResult, unitsResult] = await Promise.allSettled([
      needUsers ? getAllUsers() : Promise.resolve(previous.users ?? []),
      needUnits ? getUnitList() : Promise.resolve(previous.units ?? []),
    ]);

    const next: CachedCommonPartial = { ...previous };
    if (
      needUsers &&
      usersResult.status === 'fulfilled' &&
      Array.isArray(usersResult.value)
    ) {
      next.users = usersResult.value;
      next.usersReady = true;
    }
    if (
      needUnits &&
      unitsResult.status === 'fulfilled' &&
      Array.isArray(unitsResult.value)
    ) {
      next.units = unitsResult.value;
      next.unitsReady = true;
    }

    commonDataCache.set(key, next);
    return toMonitorCommonData(next);
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
