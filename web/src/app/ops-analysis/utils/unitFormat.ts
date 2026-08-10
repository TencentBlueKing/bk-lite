/**
 * 结构化单位库 —— 对齐 Grafana 的「单位分类 + 自动量纲缩放」。
 *
 * 用 formatUnit(value, unitId, opts) 取代旧的纯文本后缀拼接：
 *   - bytesIEC / bytesSI：数据量，自动 KiB/MiB/GiB（1024）或 KB/MB/GB（1000）
 *   - bps：数据速率（bps/Kbps/Mbps/Gbps）
 *   - ms：时间（ms→s→m→h→d 自动进位）
 *   - percent（0~100）/ percentunit（0~1）
 *   - short：计数自动缩放（1.2K / 3.4M / 5.6B）
 *   - none：原样；custom:<后缀>：原样 + 自定义后缀（兼容旧自由文本 unit）
 */

export interface UnitFormatResult {
  /** 完整展示文本，如 "1.5 KiB"、"42%" */
  text: string;
  /** 缩放并格式化后的数值部分，如 "1.5" */
  value: string;
  /** 单位后缀，如 "KiB"、"%"，none 为 "" */
  suffix: string;
}

export interface FormatOptions {
  /** 固定小数位；未设时按有效位智能截断（最多 2 位并去尾零） */
  decimals?: number;
  /** 换算系数，先乘后缩放（兼容旧 conversionFactor） */
  conversionFactor?: number;
}

interface UnitStep {
  factor: number;
  suffix: string;
}

interface UnitFamily {
  /** 数值与单位间是否加空格（数据/速率/时间加，百分比/计数不加） */
  space: boolean;
  /** 由大到小的量纲阶梯 */
  steps: UnitStep[];
}

const IEC = 1024;
const SI = 1000;

const FAMILIES: Record<string, UnitFamily> = {
  bytesIEC: {
    space: true,
    steps: [
      { factor: IEC ** 5, suffix: 'PiB' },
      { factor: IEC ** 4, suffix: 'TiB' },
      { factor: IEC ** 3, suffix: 'GiB' },
      { factor: IEC ** 2, suffix: 'MiB' },
      { factor: IEC, suffix: 'KiB' },
      { factor: 1, suffix: 'B' },
    ],
  },
  bytesSI: {
    space: true,
    steps: [
      { factor: SI ** 5, suffix: 'PB' },
      { factor: SI ** 4, suffix: 'TB' },
      { factor: SI ** 3, suffix: 'GB' },
      { factor: SI ** 2, suffix: 'MB' },
      { factor: SI, suffix: 'KB' },
      { factor: 1, suffix: 'B' },
    ],
  },
  bps: {
    space: true,
    steps: [
      { factor: SI ** 4, suffix: 'Tbps' },
      { factor: SI ** 3, suffix: 'Gbps' },
      { factor: SI ** 2, suffix: 'Mbps' },
      { factor: SI, suffix: 'Kbps' },
      { factor: 1, suffix: 'bps' },
    ],
  },
  // 时间：输入单位为毫秒
  ms: {
    space: true,
    steps: [
      { factor: 86400000, suffix: 'd' },
      { factor: 3600000, suffix: 'h' },
      { factor: 60000, suffix: 'm' },
      { factor: 1000, suffix: 's' },
      { factor: 1, suffix: 'ms' },
    ],
  },
  short: {
    space: false,
    steps: [
      { factor: SI ** 4, suffix: 'T' },
      { factor: SI ** 3, suffix: 'B' },
      { factor: SI ** 2, suffix: 'M' },
      { factor: SI, suffix: 'K' },
      { factor: 1, suffix: '' },
    ],
  },
};

const EMPTY: UnitFormatResult = { text: '--', value: '--', suffix: '' };

/** 智能格式化：固定小数位优先，否则最多 2 位有效小数并去尾零。 */
const formatNumber = (n: number, decimals?: number): string => {
  if (decimals !== undefined && decimals !== null) {
    return n.toFixed(decimals);
  }
  // 四舍五入到最多 2 位小数，去掉尾随 0 和多余小数点
  const rounded = Math.round(n * 100) / 100;
  let s = rounded.toFixed(2);
  s = s.replace(/\.?0+$/, '');
  return s === '' || s === '-0' ? '0' : s;
};

const scaleByFamily = (
  value: number,
  family: UnitFamily,
  decimals?: number
): { value: string; suffix: string } => {
  const abs = Math.abs(value);
  const step =
    family.steps.find((s) => abs >= s.factor) ||
    family.steps[family.steps.length - 1];
  return {
    value: formatNumber(value / step.factor, decimals),
    suffix: step.suffix,
  };
};

/**
 * 主入口。unitId 形如：
 *   'bytesIEC' | 'bytesSI' | 'bps' | 'ms' | 'percent' | 'percentunit'
 *   | 'short' | 'none' | 'custom:<后缀>'
 * 未识别的 unitId 一律按 custom 后缀处理（兼容旧自由文本 unit）。
 */
export const formatUnit = (
  value: number | string | null | undefined,
  unitId?: string,
  opts: FormatOptions = {}
): UnitFormatResult => {
  if (value === null || value === undefined || value === '') {
    return EMPTY;
  }

  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(num)) {
    return { text: String(value), value: String(value), suffix: '' };
  }

  const factor = opts.conversionFactor ?? 1;
  const working = num * factor;
  const id = unitId && unitId.trim() ? unitId.trim() : 'none';

  // 百分比
  if (id === 'percent' || id === 'percentunit') {
    const pct = id === 'percentunit' ? working * 100 : working;
    const v = formatNumber(pct, opts.decimals);
    return { text: `${v}%`, value: v, suffix: '%' };
  }

  // none：原样无后缀
  if (id === 'none') {
    const v = formatNumber(working, opts.decimals);
    return { text: v, value: v, suffix: '' };
  }

  // 自定义后缀：custom:<后缀>，或任何未识别 id 作为字面后缀（兼容旧 unit 文本）
  const family = FAMILIES[id];
  if (!family) {
    const suffix = id.startsWith('custom:') ? id.slice('custom:'.length) : id;
    const v = formatNumber(working, opts.decimals);
    return { text: `${v}${suffix}`, value: v, suffix };
  }

  // 结构化单位族：自动量纲缩放
  const { value: v, suffix } = scaleByFamily(working, family, opts.decimals);
  const sep = family.space ? ' ' : '';
  return { text: `${v}${sep}${suffix}`, value: v, suffix };
};

export interface UnitDef {
  id: string;
  label: string;
}
export interface UnitCategory {
  key: string;
  label: string;
  units: UnitDef[];
}

/** 供配置 UI 下拉分组渲染的单位目录。 */
export const getUnitCategories = (): UnitCategory[] => [
  {
    key: 'misc',
    label: '通用',
    units: [
      { id: 'none', label: '无单位' },
      { id: 'short', label: '计数（自动 K/M/B）' },
      { id: 'percent', label: '百分比 (0-100)' },
      { id: 'percentunit', label: '百分比 (0.0-1.0)' },
    ],
  },
  {
    key: 'data',
    label: '数据量',
    units: [
      { id: 'bytesIEC', label: '字节 (IEC, 1024)' },
      { id: 'bytesSI', label: '字节 (SI, 1000)' },
    ],
  },
  {
    key: 'throughput',
    label: '速率',
    units: [{ id: 'bps', label: '比特/秒 (bps)' }],
  },
  {
    key: 'time',
    label: '时间',
    units: [{ id: 'ms', label: '毫秒 (自动进位)' }],
  },
];
