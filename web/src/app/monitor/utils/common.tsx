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
  OrganizationNode
} from '@/app/monitor/types';
import { Group } from '@/types';
import {
  APPOINT_METRIC_IDS,
  OBJECT_DEFAULT_ICON
} from '@/app/monitor/constants';
import { isDerivativeObject } from '@/app/monitor/utils/monitorObject';
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
        node.value
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
      children: []
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

// 柱形图或者折线图单条线时，获取其最大值、最小值、平均值和最新值
export const calculateMetrics = (
  data: Record<string, number | null | undefined>[],
  key = 'value1'
) => {
  if (!data || data.length === 0) return {};
  const values = data
    .map((item) => item[key])
    .filter(
      (val): val is number =>
        typeof val === 'number' && !isNaN(val) && val !== null
    );
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
    latestValue
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

export const transformTreeData = (nodes: Group[]): CascaderItem[] => {
  return nodes.map((node) => {
    const transformedNode: CascaderItem = {
      value: node.id,
      label: node.name,
      children: []
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

  // 值会被拼进 PromQL 正则匹配器 key=~"v1|v2",必须逐个转义正则元字符,
  // 再转义 PromQL 字符串中的反斜杠和双引号,
  // 否则含 . + ( ) 等字符的实例标识(如 IP/主机名)会被当作正则,匹配到错误/多余的序列,
  // 含 " 的值还会直接破坏查询语法。
  const escapeRegexValue = (v: string): string =>
    v.replace(/[\\^$.*+?()[\]{}|]/g, '\\$&')
      .replace(/\\/g, '\\\\')
      .replace(/"/g, '\\"');

  const resultArray: string[] = [];
  for (const key in mergedObject) {
    const values = Array.from(mergedObject[key])
      .map((v) => escapeRegexValue(String(v ?? '')))
      .join('|');
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
  const seriesKeyToValueKey = new Map<string, string>();
  const getSeriesKey = (metric: Record<string, string>) => {
    const identityKeys = Array.from(
      new Set([
        ...(config[0]?.instance_id_keys || []),
        ...target.map((item) => item.name),
      ])
    );
    const identityEntries = identityKeys
      .filter((key) => Object.prototype.hasOwnProperty.call(metric || {}, key))
      .map((key) => [key, metric[key]]);

    return JSON.stringify(
      (identityEntries.length ? identityEntries : Object.entries(metric || {}))
        .sort(([left], [right]) => left.localeCompare(right))
    );
  };
  const getValueKey = (metric: Record<string, string>) => {
    const seriesKey = getSeriesKey(metric);
    const existingKey = seriesKeyToValueKey.get(seriesKey);
    if (existingKey) {
      return existingKey;
    }
    const valueKey = `value${seriesKeyToValueKey.size + 1}`;
    seriesKeyToValueKey.set(seriesKey, valueKey);
    return valueKey;
  };

  data.forEach((item) => {
    const valueKey = getValueKey(item.metric);
    item.values.forEach(([timestamp, value]) => {
      const numericValue = parseFloat(value);
      if (!Number.isFinite(numericValue)) {
        return;
      }
      const existing = result.find((entry) => entry.time === timestamp);
      const detailValue = Object.entries(item.metric)
        .map(([key, dimenValue]) => ({
          name: key,
          label: target.find((sec) => sec.name === key)?.description || key,
          value: dimenValue
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
            )?.instance_name || '--'
        });
      }
      if (existing) {
        existing[valueKey] = numericValue;
        existing.seriesMetrics = {
          ...(existing.seriesMetrics || {}),
          [valueKey]: item.metric
        };
        if (!existing.details) {
          existing.details = {};
        }
        if (!existing.details[valueKey]) {
          existing.details[valueKey] = [];
        }
        existing.details[valueKey].push(...detailValue);
      } else {
        const details = {
          [valueKey]: detailValue
        };
        result.push({
          time: timestamp,
          title: config[0]?.title || '--',
          [valueKey]: numericValue,
          seriesMetrics: {
            [valueKey]: item.metric
          },
          details
        });
      }
    });
  });
  return result.sort((left, right) => left.time - right.time);
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

// 展示监控示例名称
// 注意：objectItem 必须包含 level 字段，或者传入 objects 参数进行动态判断
export const showInstName = (
  objectItem: ObjectItem,
  row: TableDataItem,
  objects?: ObjectItem[]
) => {
  const isDerivative = objects
    ? isDerivativeObject(objectItem, objects)
    : isDerivativeObject(objectItem);
  return (
    (isDerivative ? row?.instance_id_values?.[1] : row?.instance_name) || '--'
  );
};

// 监控实例名称处理
export const getBaseInstanceColumn = (config: {
  row: ObjectItem;
  objects: ObjectItem[];
  t: any;
  queryData?: any[];
}) => {
  const baseTarget = config.objects
    .filter((item) => item.type === config.row?.type)
    .find((item) => item.level === 'base');
  const title = baseTarget?.display_name || config.t('monitor.source');
  const isDerivative = isDerivativeObject(config.row, config.objects);
  const columnItems: any = [
    {
      title: config.t('common.name'),
      dataIndex: 'instance_name',
      onCell: () => ({
        style: {
          minWidth: 150
        }
      }),
      key: 'instance_name',
      render: (_: unknown, record: TableDataItem) => {
        const instanceName = showInstName(config.row, record, config.objects);
        return (
          <EllipsisWithTooltip
            text={instanceName}
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          ></EllipsisWithTooltip>
        );
      }
    }
  ];
  if (isDerivative) {
    columnItems.unshift({
      title: title,
      dataIndex: 'base_instance_name',

      onCell: () => ({
        style: {
          minWidth: 150
        }
      }),
      key: 'base_instance_name',
      render: (_: unknown, record: TableDataItem) => {
        const instanceIdValue = record.instance_id_values?.[0];
        let displayName = instanceIdValue || '--';
        if (config.queryData && instanceIdValue) {
          const matchedItem = config.queryData.find(
            (item: TableDataItem) => item.id === instanceIdValue
          );
          if (matchedItem) {
            displayName = matchedItem.name || matchedItem.id;
          }
        }
        return (
          <EllipsisWithTooltip
            text={displayName}
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          ></EllipsisWithTooltip>
        );
      }
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

// 品牌专属采集模板/实例（如思科交换机）的品牌识别：按名称匹配 → 提供品牌标签（及可选 logo 图标）。
// icon 可选：未提供时集成卡片回退到监控对象默认图标，仪表盘头部仍展示品牌文字标签。
const BRANDS: { match: RegExp; label: string; icon?: string }[] = [
  { match: /cisco/i, label: 'Cisco', icon: 'mm-cisco_思科' },
  { match: /huawei/i, label: 'Huawei', icon: 'mm-huawei_华为' },
  { match: /aruba/i, label: 'Aruba', icon: 'mm-aruba_aruba' },
  { match: /juniper/i, label: 'Juniper', icon: 'mm-juniper_juniper' },
  { match: /extreme/i, label: 'Extreme', icon: 'mm-extreme_extreme' },
  { match: /brocade/i, label: 'Brocade', icon: 'mm-brocade_brocade' },
  { match: /\bnokia\b|omniswitch/i, label: 'Nokia', icon: 'mm-nokia_nokia' },
  { match: /alcatel|sr.?linux|srlinux|timos|\b7750\b|\b7450\b|\b7950\b/i, label: 'Alcatel-Lucent', icon: 'mm-alcatel_alcatel' },
  { match: /mikrotik/i, label: 'MikroTik', icon: 'mm-mikrotik_mikrotik' },
  { match: /dlink|d-link/i, label: 'D-Link', icon: 'mm-dlink_dlink' },
  { match: /netgear/i, label: 'NETGEAR', icon: 'mm-netgear_netgear' },
  { match: /tplink|tp-link/i, label: 'TP-Link', icon: 'mm-tplink_tplink' },
  { match: /zyxel/i, label: 'Zyxel', icon: 'mm-zyxel_zyxel' },
  { match: /qtech/i, label: 'QTech', icon: 'mm-qtech_qtech' },
  { match: /dellforce|force10|dell.?force/i, label: 'Dell Force10', icon: 'mm-dellforce_dellforce' },
  { match: /hphpn|procurve|hp.?networking/i, label: 'HP ProCurve', icon: 'mm-hphpn_hphpn' },
  { match: /fortinet|fortigate/i, label: 'Fortinet', icon: 'mm-fortinet_fortinet' },
  { match: /checkpoint|check.?point/i, label: 'Check Point', icon: 'mm-checkpoint_checkpoint' },
  { match: /stormshield/i, label: 'Stormshield', icon: 'mm-stormshield_stormshield' },
  { match: /paloalto|palo.?alto|pan.?os/i, label: 'Palo Alto', icon: 'mm-paloalto_paloalto' },
  { match: /sonicwall|sonicos/i, label: 'SonicWall', icon: 'mm-sonicwall_sonicwall' },
  { match: /watchguard|fireware/i, label: 'WatchGuard', icon: 'mm-watchguard_watchguard' },
  { match: /pfsense/i, label: 'pfSense', icon: 'mm-pfsense_pfsense' },
  { match: /opnsense/i, label: 'OPNsense', icon: 'mm-opnsense_opnsense' },
  { match: /\bf5\b|big-?ip/i, label: 'F5', icon: 'mm-f5_f5' },
  { match: /hillstone|stoneos/i, label: 'Hillstone', icon: 'mm-hillstone_hillstone' },
  { match: /sophos|\bxg\b|sfos|cyberoam/i, label: 'Sophos XG', icon: 'mm-sophos_sophos' },
  { match: /neteye|leadsec|网御/i, label: 'Neteye', icon: 'mm-neteye_neteye' },
  { match: /bluedon|蓝盾/i, label: 'Bluedon', icon: 'mm-bluedon_bluedon' },
  { match: /pulse\s*secure|ivanti|pulsesecure/i, label: 'Pulse Secure', icon: 'mm-pulsesecure_pulsesecure' },
  { match: /\bdptech\b|迪普/i, label: 'DPtech', icon: 'mm-dptech_dptech' },
  { match: /westone|卫士通/i, label: 'Westone', icon: 'mm-westone_westone' },
  { match: /amaranten|安然/i, label: 'Amaranten', icon: 'mm-amaranten_amaranten' },
  { match: /secworld|安世/i, label: 'Secworld', icon: 'mm-secworld_secworld' },
  { match: /superiority|超数/i, label: 'Superiority', icon: 'mm-superiority_superiority' },
  { match: /relianoid|\bzva\b/i, label: 'RELIANOID', icon: 'mm-relianoid_relianoid' },
  { match: /harbour|港湾/i, label: 'Harbour Networks', icon: 'mm-harbour_harbour' },
  { match: /aethra|dolcevita/i, label: 'Aethra', icon: 'mm-aethra_aethra' },
  { match: /velocloud|vmware\s*sd-?wan|\bvce\b/i, label: 'VeloCloud', icon: 'mm-velocloud_velocloud' },
  { match: /benu|benu\s*networks|\bmeg\d+/i, label: 'Benu Networks', icon: 'mm-benu_benu' },
  { match: /forcepoint|stonesoft|stonegate|ngfw/i, label: 'Forcepoint', icon: 'mm-forcepoint_forcepoint' },
  { match: /screenos|netscreen|\bssg\b/i, label: 'Juniper ScreenOS', icon: 'mm-screenos_screenos' },
  { match: /barracuda/i, label: 'Barracuda', icon: 'mm-barracuda_barracuda' },
  { match: /netscaler|citrix/i, label: 'Citrix NetScaler', icon: 'mm-netscaler_netscaler' },
  { match: /\ba10\b|thunder|acos/i, label: 'A10 Thunder', icon: 'mm-a10_a10' },
  { match: /fortiadc|fad\b/i, label: 'FortiADC', icon: 'mm-fortiadc_fortiadc' },
  { match: /alteon|radware/i, label: 'Radware Alteon', icon: 'mm-alteon_alteon' },
  { match: /vyatta|vyos/i, label: 'Vyatta', icon: 'mm-vyatta_vyatta' },
  { match: /\bnec\b|univerge|\bix[0-9]{3,4}\b/i, label: 'NEC', icon: 'mm-nec_nec' },
  { match: /draytek|vigor/i, label: 'DrayTek', icon: 'mm-draytek_draytek' },
  { match: /datacom|dmos/i, label: 'Datacom', icon: 'mm-datacom_datacom' },
  { match: /eltex/i, label: 'Eltex', icon: 'mm-eltex_eltex' },
  { match: /\bsnr\b|nag-mib/i, label: 'SNR', icon: 'mm-snr_snr' },
  { match: /apresia/i, label: 'APRESIA', icon: 'mm-apresia_apresia' },
  { match: /intelbras/i, label: 'Intelbras', icon: 'mm-intelbras_intelbras' },
  { match: /nexans/i, label: 'Nexans', icon: 'mm-nexans_nexans' },
  { match: /pica8|picos/i, label: 'Pica8', icon: 'mm-pica8_pica8' },
  { match: /advantech|\beki\b/i, label: 'Advantech', icon: 'mm-advantech_advantech' },
  { match: /etherwan/i, label: 'EtherWAN', icon: 'mm-etherwan_etherwan' },
  { match: /sixnet|\bslx\b/i, label: 'Sixnet', icon: 'mm-sixnet_sixnet' },
  { match: /allnet|\ball-sg\b/i, label: 'ALLNET', icon: 'mm-allnet_allnet' },
  { match: /redlion|red\s*lion|n-?tron/i, label: 'Red Lion', icon: 'mm-redlion_redlion' },
  { match: /alaxala|\bax2[0-9]{3}s\b/i, label: 'Alaxala', icon: 'mm-alaxala_alaxala' },
  { match: /transition\s*networks?|\bsispm\b|\bionmm\b/i, label: 'Transition Networks', icon: 'mm-transition_transition' },
  { match: /waystream|asr[0-9]+|ftth/i, label: 'Waystream', icon: 'mm-waystream_waystream' },
  { match: /tsntec|8148sc/i, label: 'TsnTec', icon: 'mm-tsntec_tsntec' },
  { match: /antaira|aaxeon|\blmx\b/i, label: 'Antaira', icon: 'mm-antaira_antaira' },
  { match: /\bwago\b|852-?1305/i, label: 'WAGO', icon: 'mm-wago_wago' },
  { match: /asterfusion|asternos/i, label: 'AsterFusion', icon: 'mm-asterfusion_asterfusion' },
  { match: /wi-?tek|wireless-tek/i, label: 'Wi-Tek', icon: 'mm-witek_witek' },
  { match: /multitech|multiconnect|\brcell\b/i, label: 'MultiTech', icon: 'mm-multitech_multitech' },
  { match: /\bavici\b/i, label: 'Avici', icon: 'mm-avici_avici' },
  { match: /unisphere|\berx\b/i, label: 'Unisphere', icon: 'mm-unisphere_unisphere' },
  { match: /6wind|\bvsr\b/i, label: '6WIND VSR', icon: 'mm-6wind_6wind' },
  { match: /sierra\s*wireless|airlink|\baleos\b/i, label: 'Sierra Wireless', icon: 'mm-sierrawireless_sierrawireless' },
  { match: /netmodule/i, label: 'NetModule', icon: 'mm-netmodule_netmodule' },
  { match: /engenius/i, label: 'EnGenius', icon: 'mm-engenius_engenius' },
  { match: /aerohive|hiveap|hiveos/i, label: 'Aerohive', icon: 'mm-aerohive_aerohive' },
  { match: /grandstream|\bgwn\d/i, label: 'Grandstream', icon: 'mm-grandstream_grandstream' },
  { match: /albentia|aerdocsis|wimax/i, label: 'Albentia', icon: 'mm-albentia_albentia' },
  { match: /ligowave|ligo\s*wave|infinity/i, label: 'LigoWave', icon: 'mm-ligowave_ligowave' },
  { match: /radwin|winlink/i, label: 'Radwin', icon: 'mm-radwin_radwin' },
  { match: /mimosa|\bbfive\b|\bptmp\b/i, label: 'Mimosa', icon: 'mm-mimosa_mimosa' },
  { match: /phoenix\s*contact|fl\s*switch/i, label: 'Phoenix Contact', icon: 'mm-phoenixcontact_phoenixcontact' },
  { match: /synology|diskstation|rackstation|\bdsm\b/i, label: 'Synology', icon: 'mm-synology_synology' },
  { match: /macrosan|\bms[0-9]{3,4}\b/i, label: 'MacroSAN', icon: 'mm-macrosan_macrosan' },
  { match: /sugon|parastor/i, label: 'Sugon', icon: 'mm-sugon_sugon' },
  { match: /netapp|ontap|\bfas[0-9]|\baff\b/i, label: 'NetApp', icon: 'mm-netapp_netapp' },
  { match: /fujitsu|eternus/i, label: 'Fujitsu', icon: 'mm-fujitsu_fujitsu' },
  { match: /inspur|as5500/i, label: 'Inspur', icon: 'mm-inspur_inspur' },
  { match: /ceresdata|ceres\s*data|希磁/i, label: 'CeresData', icon: 'mm-ceresdata_ceresdata' },
  { match: /dell\s*sc|sc8000|compellent/i, label: 'Dell SC8000', icon: 'mm-dellsc8000_dellsc8000' },
  { match: /powervault|equallogic|dell\s*ps|dell\s*md/i, label: 'Dell PowerVault', icon: 'mm-dellpowervault_dellpowervault' },
  { match: /hikvision|brainware|海康/i, label: 'Hikvision', icon: 'mm-hikvision_hikvision' },
  { match: /zdns|zddi|中国互联网研究院/i, label: 'ZDNS', icon: 'mm-zdns_zdns' },
  { match: /arris|cadant|e6\s*cmts/i, label: 'ARRIS Cadant', icon: 'mm-arris_arris' },
  { match: /vsolution|v-?sol|v1600d/i, label: 'V-SOL', icon: 'mm-vsolution_vsolution' },
  { match: /zhone|\bdzs\b|dasan/i, label: 'Zhone DZS', icon: 'mm-zhone_zhone' },
  { match: /utstarcom|utstar\s*com|\butstar\b/i, label: 'UTStarcom', icon: 'mm-utstarcom_utstarcom' },
  { match: /raisecom|roap|iscom/i, label: 'Raisecom', icon: 'mm-raisecom_raisecom' },
  { match: /packetfront|\bdrg\b/i, label: 'PacketFront', icon: 'mm-packetfront_packetfront' },
  { match: /c-?data|cdatatec/i, label: 'C-Data', icon: 'mm-cdata_cdata' },
  { match: /nateks|megatrans|orion/i, label: 'Nateks', icon: 'mm-nateks_nateks' },
  { match: /blockbit/i, label: 'Blockbit', icon: 'mm-blockbit_blockbit' },
  { match: /ascom|ip-?dect/i, label: 'Ascom', icon: 'mm-ascom_ascom' },
  { match: /parks/i, label: 'Parks', icon: 'mm-parks_parks' },
  { match: /ubiquiti|ubnt|edgeswitch/i, label: 'Ubiquiti', icon: 'mm-ubiquiti_ubiquiti' },
  { match: /ruijie|reyee|\brg-?nos\b/i, label: 'Ruijie', icon: 'mm-ruijie_ruijie' },
  { match: /\bzte\b|zxr10/i, label: 'ZTE', icon: 'mm-zte_zte' },
  { match: /omniswitch|alcatel.?os|\baos\b/i, label: 'Alcatel OmniSwitch', icon: 'mm-omniswitch_omniswitch' },
  { match: /yamaha|\bswx\b/i, label: 'Yamaha', icon: 'mm-yamaha_yamaha' },
  { match: /arista|\beos\b|dcs-/i, label: 'Arista', icon: 'mm-arista_arista' },
  { match: /mellanox|nvidia|spectrum|onyx|mlnx|\bsn[0-9]{4}\b/i, label: 'Mellanox', icon: 'mm-mellanox_mellanox' },
  { match: /allied|awplus|aw\+|at-/i, label: 'Allied Telesis', icon: 'mm-alliedtelesis_alliedtelesis' },
  { match: /os10|smartfabric|\bz9[0-9]|powerswitch/i, label: 'Dell OS10', icon: 'mm-dellos10_dellos10' },
  { match: /cnos|lenovo|thinksystem|\bne[0-9]{4}\b/i, label: 'Lenovo CNOS', icon: 'mm-lenovocnos_lenovocnos' },
  { match: /fortiswitch|fsw|fortinet.*switch/i, label: 'FortiSwitch', icon: 'mm-fortiswitch_fortiswitch' },
  { match: /fiberhome|烽火|\bwri\b/i, label: 'FiberHome', icon: 'mm-fiberhome_fiberhome' },
  { match: /\bh3c\b|comware|hh3c/i, label: 'H3C', icon: 'mm-h3c_h3c' },
  { match: /hirschmann|belden|\brs[234]0\b|greyhound/i, label: 'Hirschmann', icon: 'mm-hirschmann_hirschmann' },
  { match: /3com|a3com/i, label: '3Com', icon: 'mm-3com_3com' },
  { match: /adtran|netvanta|adtran.?aos/i, label: 'Adtran', icon: 'mm-adtran_adtran' },
  { match: /lancom|lcos/i, label: 'LANCOM', icon: 'mm-lancom_lancom' },
  { match: /\bdcn\b|digital.?china/i, label: 'DCN', icon: 'mm-dcn_dcn' },
  { match: /\bfs\b|fs\.com/i, label: 'FS', icon: 'mm-fs_fs' },
  { match: /netonix/i, label: 'Netonix', icon: 'mm-netonix_netonix' },
  { match: /audiocodes/i, label: 'AudioCodes', icon: 'mm-audiocodes_audiocodes' },
  { match: /ribbon|sonus|genband/i, label: 'Ribbon', icon: 'mm-ribbon_ribbon' },
  { match: /acme\s*packet|acmepacket/i, label: 'Acme Packet', icon: 'mm-acmepacket_acmepacket' },
  { match: /patton|smartnode/i, label: 'Patton', icon: 'mm-patton_patton' },
  { match: /innovaphone/i, label: 'Innovaphone', icon: 'mm-innovaphone_innovaphone' },
  { match: /mitel|mivoice|3300\s*icp/i, label: 'Mitel', icon: 'mm-mitel_mitel' },
  { match: /opengear/i, label: 'Opengear', icon: 'mm-opengear_opengear' },
  { match: /avocent|cyclades|\bacs[0-9]{3,4}\b/i, label: 'Avocent ACS', icon: 'mm-avocent_avocent' },
  { match: /perle|iolan|\bscg[0-9]*\b/i, label: 'Perle IOLAN', icon: 'mm-perle_perle' },
  { match: /raritan|dominion\s*sx|\bsx\s*ii\b/i, label: 'Raritan SX', icon: 'mm-raritan_raritan' },
  { match: /infoblox/i, label: 'Infoblox', icon: 'mm-infoblox_infoblox' },
  { match: /bluecat|bcn-|ddi/i, label: 'BlueCat', icon: 'mm-bluecat_bluecat' },
  { match: /meinberg|lantime/i, label: 'Meinberg', icon: 'mm-meinberg_meinberg' },
  { match: /endace/i, label: 'Endace', icon: 'mm-endace_endace' },
  { match: /deva\s*broadcast|\bdeva\b/i, label: 'DEVA Broadcast', icon: 'mm-deva_deva' },
  { match: /endrun|sonoma|tempus/i, label: 'EndRun', icon: 'mm-endrun_endrun' },
  { match: /spectracom|orolia|securesync|netclock/i, label: 'Spectracom', icon: 'mm-spectracom_spectracom' },
  { match: /asentria|siteboss/i, label: 'Asentria', icon: 'mm-asentria_asentria' },
  { match: /server\s*technology|servertech|sentry3/i, label: 'Server Technology', icon: 'mm-servertech_servertech' },
  { match: /enlogic|en2\.?0/i, label: 'Enlogic', icon: 'mm-enlogic_enlogic' },
  { match: /rittal|cmc\s*iii/i, label: 'Rittal', icon: 'mm-rittal_rittal' },
  { match: /gude|expert\s*power\s*control/i, label: 'Gude', icon: 'mm-gude_gude' },
  { match: /geist|blackbird|watchdog/i, label: 'Geist', icon: 'mm-geist_geist' },
  { match: /panduit/i, label: 'Panduit', icon: 'mm-panduit_panduit' },
  { match: /apc|schneider\s*electric|powernet/i, label: 'APC', icon: 'mm-apc_apc' },
  { match: /eaton|powerware|xups/i, label: 'Eaton', icon: 'mm-eaton_eaton' },
  { match: /socomec|net\s*vision/i, label: 'Socomec', icon: 'mm-socomec_socomec' },
  { match: /liebert|vertiv/i, label: 'Liebert', icon: 'mm-liebert_liebert' },
  { match: /wti|western\s*telematic/i, label: 'WTI', icon: 'mm-wti_wti' },
  { match: /\bnti\b|enviromux/i, label: 'NTI ENVIROMUX', icon: 'mm-nti_nti' },
  { match: /gigamon|gigavue/i, label: 'Gigamon' },
  { match: /accedian|skylight|metronid/i, label: 'Accedian', icon: 'mm-accedian_accedian' },
  { match: /cradlepoint|netcloud/i, label: 'Cradlepoint' },
  { match: /ciena/i, label: 'Ciena', icon: 'mm-ciena_ciena' },
  { match: /saf\s*tehnika|saftehnika|integra-[a-z0-9]+/i, label: 'SAF Tehnika', icon: 'mm-saftehnika_saftehnika' },
  { match: /\bmrv\b|optidriver|in-?reach/i, label: 'MRV', icon: 'mm-mrv_mrv' },
  { match: /marconi/i, label: 'Marconi', icon: 'mm-marconi_marconi' },
  { match: /alcoma/i, label: 'Alcoma', icon: 'mm-alcoma_alcoma' },
  { match: /\bsiae\b|microelettronica/i, label: 'SIAE Microelettronica', icon: 'mm-siae_siae' },
  { match: /packetlight|packet\s*light|pl-[0-9a-z-]+/i, label: 'PacketLight', icon: 'mm-packetlight_packetlight' },
  { match: /pan\s*dacom|pandacom/i, label: 'Pan Dacom', icon: 'mm-pandacom_pandacom' },
  { match: /tachyon|\btna\s*300|tna30x/i, label: 'Tachyon', icon: 'mm-tachyon_tachyon' },
  { match: /\bxkl\b|dxmos|dqt400|dqm400/i, label: 'XKL', icon: 'mm-xkl_xkl' },
  { match: /siklu|etherhaul|multihaul/i, label: 'Siklu', icon: 'mm-siklu_siklu' },
  { match: /4rf|aprisa/i, label: '4RF Aprisa', icon: 'mm-4rf_4rf' },
  { match: /viavi|jdsu|acterna/i, label: 'Viavi', icon: 'mm-viavi_viavi' },
  { match: /sycamore/i, label: 'Sycamore', icon: 'mm-sycamore_sycamore' },
  { match: /ekinops/i, label: 'Ekinops', icon: 'mm-ekinops_ekinops' },
  { match: /infinera|coriant|groove/i, label: 'Infinera', icon: 'mm-infinera_infinera' },
  { match: /bridgewave|flexport|fe80/i, label: 'BridgeWave', icon: 'mm-bridgewave_bridgewave' },
  { match: /huber\s*\+?\s*suhner|cubo\s*mini|cube\s*optics/i, label: 'Huber+Suhner Cubo', icon: 'mm-hubersuhner_hubersuhner' },
  { match: /fibrolan|falcon/i, label: 'Fibrolan', icon: 'mm-fibrolan_fibrolan' },
  { match: /smartoptics/i, label: 'Smartoptics', icon: 'mm-smartoptics_smartoptics' },
  { match: /racom|\bray\b/i, label: 'RACOM', icon: 'mm-racom_racom' },
  { match: /exalt|ex-i|exaltcom/i, label: 'Exalt', icon: 'mm-exalt_exalt' },
  { match: /bdcom/i, label: 'BDCOM', icon: 'mm-bdcom_bdcom' },
  { match: /cambium/i, label: 'Cambium', icon: 'mm-cambium_cambium' },
  { match: /proxim/i, label: 'Proxim', icon: 'mm-proxim_proxim' }
];

// 按插件名取品牌 logo 图标；未命中返回 undefined（调用方回退监控对象图标）。
export const getPluginBrandIcon = (pluginName = ''): string | undefined =>
  BRANDS.find((brand) => brand.match.test(pluginName))?.icon;

// 按名称（实例名/插件名）取品牌标签（如 'Cisco'），用于在共享仪表盘头部标识当前品牌；未命中返回 undefined。
export const getBrandLabel = (text = ''): string | undefined =>
  BRANDS.find((brand) => brand.match.test(text))?.label;

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
