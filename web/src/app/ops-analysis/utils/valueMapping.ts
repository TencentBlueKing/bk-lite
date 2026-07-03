/**
 * 值映射（Value Mappings）—— 对齐 Grafana：把原始值按规则映射为展示文本和/或颜色。
 *
 * 典型场景：0→"离线"(红)、1→"在线"(绿)、范围 [0,60)→"健康"、正则匹配、
 * 以及 null/NaN/空 等特殊值的兜底展示。
 *
 * 规则按声明顺序匹配，**第一条命中即返回**（与 Grafana 一致）。
 * 纯函数、无副作用、无 IO，便于在单值/表格/拓扑节点等处复用。
 */

export type ValueMappingType = 'value' | 'range' | 'regex' | 'special';

export type SpecialMatch = 'null' | 'nan' | 'empty' | 'true' | 'false';

export interface ValueMappingResult {
  /** 命中后展示的文本（不设则沿用原值展示） */
  text?: string;
  /** 命中后应用的颜色（hex），可用于文字/背景/节点 */
  color?: string;
}

export interface ValueMapping {
  type: ValueMappingType;
  /** type=value：精确匹配的字符串（与 String(raw) 比较） */
  value?: string;
  /** type=range：数值下界（含），不设表示 -∞ */
  from?: number;
  /** type=range：数值上界（含），不设表示 +∞ */
  to?: number;
  /** type=regex：正则源串（匹配 String(raw)） */
  pattern?: string;
  /** type=special：特殊值类别 */
  match?: SpecialMatch;
  /** 命中后的展示结果 */
  result: ValueMappingResult;
}

const isEmpty = (v: unknown): boolean => v === '' ;
const isNull = (v: unknown): boolean => v === null || v === undefined;

const matchSpecial = (raw: unknown, kind?: SpecialMatch): boolean => {
  switch (kind) {
    case 'null':
      return isNull(raw);
    case 'empty':
      return isEmpty(raw);
    case 'nan':
      // 仅匹配真正的非数值：NaN 数值或字面量 "NaN"（不把 'abc'/'false' 等普通字符串算作 NaN）
      return (typeof raw === 'number' && Number.isNaN(raw)) || raw === 'NaN';
    case 'true':
      return raw === true || raw === 'true';
    case 'false':
      return raw === false || raw === 'false';
    default:
      return false;
  }
};

const matchRange = (raw: unknown, from?: number, to?: number): boolean => {
  const num = typeof raw === 'number' ? raw : parseFloat(String(raw));
  if (Number.isNaN(num)) return false;
  if (from !== undefined && from !== null && num < from) return false;
  if (to !== undefined && to !== null && num > to) return false;
  // 至少要有一个边界，避免空范围误命中一切
  return from !== undefined || to !== undefined;
};

const matchRegex = (raw: unknown, pattern?: string): boolean => {
  if (!pattern) return false;
  try {
    return new RegExp(pattern).test(String(raw));
  } catch {
    // 非法正则：忽略该规则而非抛错
    return false;
  }
};

/**
 * 按规则顺序匹配 raw，返回第一条命中规则的结果；都不命中返回 null。
 */
export const applyValueMapping = (
  raw: unknown,
  mappings?: ValueMapping[],
): ValueMappingResult | null => {
  if (!mappings || mappings.length === 0) return null;

  for (const m of mappings) {
    let hit = false;
    switch (m.type) {
      case 'value':
        hit = m.value !== undefined && String(raw) === m.value;
        break;
      case 'range':
        hit = matchRange(raw, m.from, m.to);
        break;
      case 'regex':
        hit = matchRegex(raw, m.pattern);
        break;
      case 'special':
        hit = matchSpecial(raw, m.match);
        break;
      default:
        hit = false;
    }
    if (hit) return m.result || {};
  }
  return null;
};
