import {
  GroupedUnitItem,
  GroupedUnitList,
  UnitListItem,
  UserItem,
} from '@/app/monitor/types';

interface LoadState {
  requestLoading: boolean;
  userInfoLoading: boolean;
  selectedGroupId?: string | number | null;
}

interface LoadMonitorCommonDataParams {
  getAllUsers: () => Promise<UserItem[]>;
  getUnitList: () => Promise<UnitListItem[]>;
}

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
        label: item.unit_name,
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
}: LoadMonitorCommonDataParams) => {
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

  return {
    users,
    units,
    groupedUnits: buildGroupedUnitList(units),
  };
};
