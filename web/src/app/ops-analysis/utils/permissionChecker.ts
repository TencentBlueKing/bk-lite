import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

/**
 * 检查用户是否有权限访问数据源
 * @param dataSource 数据源对象
 * @param userGroupId 当前用户的组织ID (可以是字符串或数字)
 * @returns 是否有权限
 */
export const checkDataSourceAuth = (
  dataSource: DatasourceItem,
  userGroupId?: number | string
): boolean => {
  // 如果数据源没有配置 groups，则所有人都有权限
  if (!dataSource.groups || dataSource.groups.length === 0) {
    return true;
  }

  // 如果用户没有组织信息，则无权限
  if (!userGroupId) {
    return false;
  }

  // 转换 userGroupId 为数字
  const groupId = typeof userGroupId === 'string' ? parseInt(userGroupId, 10) : userGroupId;

  // 检查用户的组织是否在数据源配置的组织列表中
  return dataSource.groups.includes(groupId);
};

/**
 * 为数据源列表添加 hasAuth 字段
 * @param dataSources 数据源列表
 * @param userGroupId 当前用户的组织ID (可以是字符串或数字)
 * @returns 带有 hasAuth 字段的数据源列表
 */
export const addAuthToDataSources = (
  dataSources: DatasourceItem[],
  userGroupId?: number | string
): DatasourceItem[] => {
  return dataSources.map((ds) => ({
    ...ds,
    hasAuth: checkDataSourceAuth(ds, userGroupId),
  }));
};
