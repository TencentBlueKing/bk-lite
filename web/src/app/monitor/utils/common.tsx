import {
  CascaderItem,
  OriginOrganization,
  OriginSubGroupItem,
  SubGroupItem,
  ListItem,
  ViewQueryKeyValuePairs,
  ChartData,
  TreeItem,
  TableDataItem,
  TimeValuesProps,
  ChartProps,
  ObjectItem,
  MetricItem,
  ChartDataItem,
  NodeWorkload,
  OrganizationNode,
  UnitItem,
} from '@/app/monitor/types';
import { Group } from '@/types';
import {
  UNIT_LIST,
  APPOINT_METRIC_IDS,
  DERIVATIVE_OBJECTS,
  OBJECT_DEFAULT_ICON,
} from '@/app/monitor/constants';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import dayjs from 'dayjs';

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
): CascaderItem[] => {
  const result: CascaderItem[] = [];
  arr.forEach((item) => {
    const newItem: CascaderItem = {
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
export const findNodeWithParents = (
  nodes: OrganizationNode[],
  id: string,
  parent: OrganizationNode | null = null
): OrganizationNode[] | null => {
  for (const node of nodes) {
    if (node.id === id) {
      if (parent) {
        const parentNodes = findNodeWithParents(nodes, parent.id);
        return parentNodes ? [node, ...parentNodes] : [node];
      }
      return [node];
    }
    if (node.subGroups && node.subGroups.length > 0) {
      const result = findNodeWithParents(node.subGroups, id, node);
      if (result) {
        return result;
      }
    }
  }
  return null;
};

// 过滤出所有给定ID的节点及其所有父级节点
export const filterNodesWithAllParents = (
  nodes: OrganizationNode[],
  ids: string[]
): OrganizationNode[] => {
  const result: OrganizationNode[] = [];
  const uniqueIds = new Set(ids);
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
export const findGroupNameById = (
  arr: Array<SubGroupItem>,
  value: unknown
): string | null => {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i].value === value) {
      return arr[i].label || null;
    }
    if (arr[i].children && arr[i].children?.length) {
      const label = findGroupNameById(arr[i]?.children || [], value);
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
  const groupNames: (string | null)[] = [];
  groupIds.forEach((el) => {
    groupNames.push(findGroupNameById(organizationList, Number(el)));
  });
  return groupNames.filter((item) => !!item).join(',') || '--';
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
  arr: UnitItem[] = UNIT_LIST
): string => {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i].value === value) {
      return arr[i].unit || '';
    }
    if (arr[i].children && arr[i].children?.length) {
      const label = findUnitNameById(value, arr[i]?.children || []);
      if (label) {
        return label;
      }
    }
  }
  return '';
};

// 柱形图或者折线图单条线时，获取其最大值、最小值、平均值和最新值
export const calculateMetrics = (
  data: Record<string, number>[],
  key = 'value1'
) => {
  if (!data || data.length === 0) return {};
  const values = data
    .map((item) => item[key])
    .filter((val): val is number => typeof val === 'number');
  if (values.length === 0) return {};

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
export const findLabelById = (data: TreeItem[], key: string): string | null => {
  for (const node of data) {
    if (node.key === key) {
      return node.label || null;
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
  const result: ChartData[] = [];
  const target = config[0]?.dimensions || [];
  data.forEach((item, index) => {
    item.values.forEach(([timestamp, value]) => {
      const existing = result.find((entry) => entry.time === timestamp);
      const detailValue = Object.entries(item.metric)
        .map(([key, dimenValue]) => ({
          name: key,
          label: target.find((sec) => sec.name === key)?.description || key,
          value: dimenValue,
        }))
        .filter((item) => target.find((tex) => tex.name === item.name));
      if (config[0]?.showInstName) {
        detailValue.unshift({
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
            )?.instance_name || '--',
        });
      }
      if (existing) {
        existing[`value${index + 1}`] = parseFloat(value);
        if (!existing.details) {
          existing.details = {};
        }
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

// 展示监控示例名称
export const showInstName = (objectItem: ObjectItem, row: TableDataItem) => {
  const isDerivative = DERIVATIVE_OBJECTS.includes(objectItem?.name);
  return (
    (isDerivative ? row?.instance_id_values?.[1] : row?.instance_name) || '--'
  );
};

// 监控实例名称处理
export const getBaseInstanceColumn = (config: {
  row: ObjectItem;
  objects: ObjectItem[];
  t: any;
}) => {
  const baseTarget = config.objects
    .filter((item) => item.type === config.row?.type)
    .find((item) => item.level === 'base');
  const title = baseTarget?.display_name || config.t('monitor.source');
  const isDerivative = DERIVATIVE_OBJECTS.includes(config.row?.name);
  const columnItems: any = [
    {
      title: config.t('common.name'),
      dataIndex: 'instance_name',
      width: 300,
      key: 'instance_name',
      render: (_: unknown, record: TableDataItem) => {
        const instanceName = showInstName(config.row, record);
        return (
          <EllipsisWithTooltip
            text={instanceName}
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          ></EllipsisWithTooltip>
        );
      },
    },
  ];
  if (isDerivative) {
    columnItems.unshift({
      title: title,
      dataIndex: 'base_instance_name',
      width: 300,
      key: 'base_instance_name',
      render: (_: unknown, record: TableDataItem) => {
        return (
          <EllipsisWithTooltip
            text={record.instance_id_values?.[0] || '--'}
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          ></EllipsisWithTooltip>
        );
      },
    });
  }
  return columnItems;
};

export const getIconByObjectName = (objectName = '', objects: ObjectItem[]) => {
  return (
    (objects.find((item) => item.name === objectName)?.icon as string) ||
    OBJECT_DEFAULT_ICON
  );
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
