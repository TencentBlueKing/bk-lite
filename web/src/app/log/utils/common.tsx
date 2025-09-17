import {
  CascaderItem,
  SubGroupItem,
  TimeValuesProps,
  TreeItem,
} from '@/app/log/types';
import { Group } from '@/types';
import { DetailItem, LogStream } from '@/app/log/types/search';
import dayjs from 'dayjs';
import React from 'react';

// 获取头像随机色
export const getRandomColor = () => {
  const colors = ['#875CFF', '#FF9214', '#00CBA6', '#1272FF'];
  const randomIndex = Math.floor(Math.random() * colors.length);
  return colors[randomIndex];
};

// 获取随机颜色
export const generateUniqueRandomColor = (() => {
  const generatedColors = new Set<string>();
  return (): string => {
    const letters = '0123456789ABCDEF';
    let color;
    do {
      color = '#';
      for (let i = 0; i < 6; i++) {
        color += letters[Math.floor(Math.random() * 16)];
      }
    } while (generatedColors.has(color));
    generatedColors.add(color);
    return color;
  };
})();

// 判断一个字符串是否是字符串的数组
export const isStringArray = (input: string): boolean => {
  try {
    if (typeof input !== 'string') {
      return false;
    }
    const parsed = JSON.parse(input);
    if (!Array.isArray(parsed)) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
};

export const transformTreeData = (nodes: Group[]): CascaderItem[] => {
  return nodes.map((node) => {
    const transformedNode: CascaderItem = {
      value: node.id,
      label: node.name,
      children: [],
    };
    if (node.children?.length) {
      transformedNode.children = transformTreeData(node.children);
    }
    return transformedNode;
  });
};

// 根据分组id找出分组名称(单个id展示)
export const findGroupNameById = (arr: Array<SubGroupItem>, value: unknown) => {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i].value === value) {
      return arr[i].label;
    }
    if (arr[i].children && arr[i].children?.length) {
      const label: unknown = findGroupNameById(arr[i]?.children || [], value);
      if (label) {
        return label;
      }
    }
  }
  return null;
};

// 根据分组id找出分组名称(多个id展示)
export const showGroupName = (
  groupIds: string[],
  organizationList: Array<SubGroupItem>
) => {
  if (!groupIds?.length) return '--';
  const groupNames: any[] = [];
  groupIds.forEach((el) => {
    groupNames.push(findGroupNameById(organizationList, Number(el)));
  });
  return groupNames.filter((item) => !!item).join(',') || '--';
};

// 日志搜索数据处理
export const aggregateLogs = (logs: LogStream[]) => {
  try {
    const timeMap = new Map<string, { value: number; details: DetailItem[] }>();

    logs.forEach((log) => {
      log.timestamps.forEach((timestamp, index) => {
        const value = log.values[index];

        if (!timeMap.has(timestamp)) {
          timeMap.set(timestamp, {
            value: 0,
            details: [],
          });
        }

        const entry = timeMap.get(timestamp)!;
        entry.value += value;
        entry.details.push({
          stream: log.fields?._stream || '--',
          value: value,
        });
      });
    });

    return Array.from(timeMap.entries()).map(([time, { value, details }]) => ({
      time: dayjs(time).valueOf(),
      value,
      detail: details,
    }));
  } catch {
    return [];
  }
};

// 数组转义
export const escapeArrayToJson = (arr: React.Key[]) => {
  return JSON.stringify(arr).replace(/"/g, '\\"');
};

// 树形组件根据id查其title
export const findLabelById = (data: any[], key: string): string | null => {
  for (const node of data) {
    if (node.key === key) {
      return node.label;
    }
    if (node.children) {
      const result = findLabelById(node.children, key);
      if (result) {
        return result;
      }
    }
  }
  return null;
};

export const findTreeParentKey = (
  treeData: TreeItem[],
  targetKey: React.Key
): React.Key | null => {
  let parentKey: React.Key | null = null;
  const loop = (nodes: TreeItem[], parent: React.Key | null) => {
    for (const node of nodes) {
      if (node.key === targetKey) {
        parentKey = parent;
        return;
      }
      if (node.children) {
        loop(node.children, node.key); // 递归遍历子节点
      }
    }
  };
  loop(treeData, null); // 初始父节点为 null
  return parentKey;
};

export const getRecentTimeRange = (timeValues: TimeValuesProps) => {
  if (timeValues.originValue) {
    const beginTime: number = dayjs()
      .subtract(timeValues.originValue, 'minute')
      .valueOf();
    const lastTime: number = dayjs().valueOf();
    return [beginTime, lastTime];
  }
  return timeValues.timeRange;
};

// 判断一个字符串是否是JSON
export const isJSON = (input: string): boolean => {
  try {
    if (typeof input !== 'string') {
      return false;
    }
    const parsed = JSON.parse(input);
    return !!parsed;
  } catch {
    return false;
  }
};
