import {
  CascaderItem,
  OriginOrganization,
  OriginSubGroupItem,
  SubGroupItem,
  ListItem,
  ViewQueryKeyValuePairs,
  ChartData,
  TreeItem,
} from '@/app/monitor/types';
import { Group } from '@/types';
import {
  MetricItem,
  ChartDataItem,
  ChartProps,
  NodeWorkload,
} from '@/app/monitor/types/monitor';
import { UNIT_LIST, APPOINT_METRIC_IDS } from '@/app/monitor/constants/monitor';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';

// 深克隆
export const deepClone = (obj: any, hash = new WeakMap()) => {
  if (Object(obj) !== obj) return obj;
  if (obj instanceof Set) return new Set(obj);
  if (hash.has(obj)) return hash.get(obj);

  const result =
    obj instanceof Date
      ? new Date(obj)
      : obj instanceof RegExp
        ? new RegExp(obj.source, obj.flags)
        : obj.constructor
          ? new obj.constructor()
          : Object.create(null);

  hash.set(obj, result);

  if (obj instanceof Map) {
    Array.from(obj, ([key, val]) => result.set(key, deepClone(val, hash)));
  }

  // 复制函数
  if (typeof obj === 'function') {
    return function (this: unknown, ...args: unknown[]): unknown {
      return obj.apply(this, args);
    };
  }

  // 递归复制对象的其他属性
  for (const key in obj) {
    if (obj.hasOwnProperty(key)) {
      // File不做处理
      if (obj[key] instanceof File) {
        result[key] = obj[key];
        continue;
      }
      result[key] = deepClone(obj[key], hash);
    }
  }

  return result;
};

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

// 针对层级组件，当值为最后一级的value时的回显，需要找到其所有父value并转成的数组格式vaule
export const findCascaderPath = (
  nodes: CascaderItem[],
  targetValue: string,
  path: Array<string | number> = []
): Array<string | number> => {
  for (const node of nodes) {
    // 如果找到目标值，返回当前路径加上目标值
    if (node.value === targetValue) {
      return [...path, node.value];
    }
    // 如果有子节点，递归查找
    if (node.children) {
      const result = findCascaderPath(node.children, targetValue, [
        ...path,
        node.value,
      ]);
      // 如果在子节点中找到了目标值，返回结果
      if (result.length) {
        return result;
      }
    }
  }
  // 如果没有找到目标值，返回空数组
  return [];
};

// 组织改造成联级数据
export const convertArray = (
  arr: Array<OriginOrganization | OriginSubGroupItem>
) => {
  const result: any = [];
  arr.forEach((item) => {
    const newItem = {
      value: item.id,
      label: item.name,
      children: [],
    };
    const subGroups: OriginSubGroupItem[] = item.subGroups;
    if (subGroups && !!subGroups.length) {
      newItem.children = convertArray(subGroups);
    }
    result.push(newItem);
  });
  return result;
};

// 用于查节点及其所有父级节点
export const findNodeWithParents: any = (
  nodes: any[],
  id: string,
  parent: any = null
) => {
  for (const node of nodes) {
    if (node.id === id) {
      return parent ? [node, ...findNodeWithParents(nodes, parent.id)] : [node];
    }
    if (node.subGroups && node.subGroups.length > 0) {
      const result: any = findNodeWithParents(node.subGroups, id, node);
      if (result) {
        return result;
      }
    }
  }
  return null;
};

// 过滤出所有给定ID的节点及其所有父级节点
export const filterNodesWithAllParents = (nodes: any, ids: any[]) => {
  const result: any[] = [];
  const uniqueIds: any = new Set(ids);
  for (const id of uniqueIds) {
    const nodeWithParents = findNodeWithParents(nodes, id);
    if (nodeWithParents) {
      for (const node of nodeWithParents) {
        if (!result.find((n) => n.id === node.id)) {
          result.push(node);
        }
      }
    }
  }
  return result;
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
    groupNames.push(findGroupNameById(organizationList, el));
  });
  return groupNames.filter((item) => !!item).join(',');
};

// 图标中x轴的时间回显处理
export const useFormatTime = () => {
  const { convertToLocalizedTime } = useLocalizedTime();
  const formatTime = (timestamp: number, minTime: number, maxTime: number) => {
    const totalTimeSpan = maxTime - minTime;
    const time = new Date(timestamp * 1000) + '';
    if (totalTimeSpan === 0) {
      return convertToLocalizedTime(time, 'YYYY-MM-DD HH:mm:ss');
    }
    if (totalTimeSpan <= 24 * 60 * 60) {
      // 如果时间跨度在一天以内，显示小时分钟
      return convertToLocalizedTime(time, 'HH:mm:ss');
    }
    if (totalTimeSpan <= 30 * 24 * 60 * 60) {
      // 如果时间跨度在一个月以内，显示月日
      return convertToLocalizedTime(time, 'MM-DD HH:mm');
    }
    if (totalTimeSpan <= 365 * 24 * 60 * 60) {
      // 如果时间跨度在一年以内，显示年月日
      return convertToLocalizedTime(time, 'YYYY-MM-DD');
    }
    // 否则显示年月
    return convertToLocalizedTime(time, 'YYYY-MM');
  };
  return { formatTime };
};

// 根据id找到单位名称（单个id展示）
export const findUnitNameById = (
  value: unknown,
  arr: Array<any> = UNIT_LIST
) => {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i].value === value) {
      return arr[i].unit;
    }
    if (arr[i].children && arr[i].children?.length) {
      const label: unknown = findUnitNameById(value, arr[i]?.children || []);
      if (label) {
        return label;
      }
    }
  }
  return '';
};

// 柱形图或者折线图单条线时，获取其最大值、最小值、平均值和最新值、和
export const calculateMetrics = (data: any[], key = 'value1') => {
  if (!data || data.length === 0) return {};
  const values = data.map((item) => item[key]);
  const maxValue = Math.max(...values);
  const minValue = Math.min(...values);
  const sumValue = values.reduce((sum, value) => sum + value, 0);
  const avgValue = sumValue / values.length;
  const latestValue = values[values.length - 1];
  return {
    maxValue,
    minValue,
    avgValue,
    sumValue,
    latestValue,
  };
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

// 根据指标枚举获取值
export const getEnumValue = (metric: MetricItem, id: number | string) => {
  const { unit: input = '', name } = metric || {};
  if (!id && id !== 0) return '--';
  if (isStringArray(input)) {
    return (
      JSON.parse(input).find((item: ListItem) => item.id === id)?.name || id
    );
  }
  return isNaN(+id) || APPOINT_METRIC_IDS.includes(name)
    ? id
    : (+id).toFixed(2);
};

// 根据指标枚举获取颜色值
export const getEnumColor = (metric: MetricItem, id: number | string) => {
  const { unit: input = '' } = metric || {};
  if (isStringArray(input)) {
    return (
      JSON.parse(input).find((item: ListItem) => item.id === +id)?.color || ''
    );
  }
  return '';
};

// 根据指标枚举获取值+单位
export const getEnumValueUnit = (metric: MetricItem, id: number | string) => {
  const { unit: input = '', name } = metric || {};
  if (!id && id !== 0) return '--';
  if (isStringArray(input)) {
    return (
      JSON.parse(input).find((item: ListItem) => item.id === +id)?.name || id
    );
  }
  const unit = findUnitNameById(input);
  return isNaN(+id) || APPOINT_METRIC_IDS.includes(name)
    ? `${id} ${unit}`
    : `${(+id).toFixed(2)} ${unit}`;
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

export const mergeViewQueryKeyValues = (
  pairs: ViewQueryKeyValuePairs[]
): string => {
  const mergedObject: { [key: string]: Set<string> } = {};
  pairs.forEach((pair) => {
    (pair.keys || []).forEach((key, index) => {
      const value = (pair.values || [])[index];
      if (!mergedObject[key]) {
        mergedObject[key] = new Set();
      }
      mergedObject[key].add(value);
    });
  });

  const resultArray: string[] = [];
  for (const key in mergedObject) {
    const values = Array.from(mergedObject[key]).join('|');
    resultArray.push(`${key}=~"${values}"`);
  }

  return resultArray.join(',');
};

export const renderChart = (
  data: ChartDataItem[],
  config: ChartProps[]
): ChartData[] => {
  const result: any[] = [];
  const target = config[0]?.dimensions || [];
  data.forEach((item, index) => {
    item.values.forEach(([timestamp, value]) => {
      const existing = result.find((entry) => entry.time === timestamp);
      let detailValue = Object.entries(item.metric)
        .map(([key, dimenValue]) => ({
          name: key,
          label: target.find((sec) => sec.name === key)?.description || key,
          value: dimenValue,
        }))
        .filter((item) => target.find((tex) => tex.name === item.name));
      if ((!target.length || !detailValue.length) && config[0]?.showInstName) {
        detailValue = [
          {
            name: 'instance_name',
            label: 'Instance',
            value:
              config.find(
                (detail) =>
                  JSON.stringify(detail.instance_id_values) ===
                  JSON.stringify(
                    detail.instance_id_keys.reduce((pre, cur) => {
                      return pre.concat(item.metric[cur] as any);
                    }, [])
                  )
              )?.instance_name || '',
          },
        ];
      }
      if (existing) {
        existing[`value${index + 1}`] = parseFloat(value);
        if (!existing.details[`value${index + 1}`]) {
          existing.details[`value${index + 1}`] = [];
        }
        existing.details[`value${index + 1}`].push(...detailValue);
      } else {
        const details = {
          [`value${index + 1}`]: detailValue,
        };
        result.push({
          time: timestamp,
          title: config[0]?.title || '--',
          [`value${index + 1}`]: parseFloat(value),
          details,
        });
      }
    });
  });
  return result;
};

export const useHandleCopy = (value: string) => {
  const { t } = useTranslation();
  const handleCopy = () => {
    try {
      if (navigator?.clipboard?.writeText) {
        navigator.clipboard.writeText(value);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = value;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      message.success(t('common.successfulCopied'));
    } catch (error: any) {
      message.error(error + '');
    }
  };
  return {
    handleCopy,
  };
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

export const getK8SData = (
  data: Record<
    string,
    Record<string, { node: string[]; workload: NodeWorkload[] }>
  >
) => {
  let result = [];
  try {
    result = Object.entries(data).map(([key, value]) => ({
      id: key,
      child: Object.entries(value).map(([innerKey, innerValue]) => ({
        id: innerKey,
        child: [
          {
            id: 'node',
            child: innerValue.node,
          },
          {
            id: 'workload',
            child: innerValue.workload,
          },
        ],
      })),
    }));
  } catch {
    return [];
  }
  return result;
};
