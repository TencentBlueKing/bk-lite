/**
 * 端口对(port_pairs)数据模型助手(design.md §2.4, §6.4)。
 *
 * 端口对显式配对:`[{source_interface, target_interface}]`,
 * 与 v0 的"按数组下标隐式 1:1 配对"等价,但 UI 与导入导出更清晰。
 *
 * 所有函数对非法输入(null/undefined/字符串)返回安全默认,不抛异常。
 */

import type {
  NetworkInterfaceRef,
  NetworkPortPair,
} from '@/app/ops-analysis/types/networkTopology';

/** 构造一对端口(显式 1:1)。 */
export function buildPortPair(
  source: NetworkInterfaceRef,
  target: NetworkInterfaceRef,
): NetworkPortPair {
  return {
    source_interface: source,
    target_interface: target,
  };
}

/** 把任意输入归一为合法 port_pair 或 null(运行时由调用方决定如何回退)。 */
export function normalizePortPair(input: unknown): NetworkPortPair | null {
  if (!input || typeof input !== 'object') return null;
  const candidate = input as Partial<NetworkPortPair>;
  if (!isValidInterfaceRef(candidate.source_interface)) return null;
  if (!isValidInterfaceRef(candidate.target_interface)) return null;
  return {
    source_interface: candidate.source_interface,
    target_interface: candidate.target_interface,
  };
}

function isValidInterfaceRef(input: unknown): input is NetworkInterfaceRef {
  if (!input || typeof input !== 'object') return false;
  const ref = input as Partial<NetworkInterfaceRef>;
  return (
    typeof ref.bk_obj_id === 'string' &&
    ref.bk_inst_id !== undefined &&
    ref.bk_inst_id !== null &&
    Number.isFinite(Number(ref.bk_inst_id)) &&
    typeof ref.interface_name === 'string' &&
    ref.interface_name.length > 0
  );
}

/** 校验完整 port_pair 数据结构。 */
export function isValidPortPair(input: unknown): input is NetworkPortPair {
  return normalizePortPair(input) !== null;
}

/** 端口对列表统计(用于运行态摘要)。 */
export function summarizePortPairs(pairs: ReadonlyArray<NetworkPortPair>): {
  count: number;
  uniqueSourceIds: number;
  uniqueTargetIds: number;
} {
  const sources = new Set<number>();
  const targets = new Set<number>();
  let count = 0;
  for (const pair of pairs) {
    count += 1;
    sources.add(Number(pair.source_interface.bk_inst_id));
    targets.add(Number(pair.target_interface.bk_inst_id));
  }
  return {
    count,
    uniqueSourceIds: sources.size,
    uniqueTargetIds: targets.size,
  };
}

/**
 * 替换/插入一对端口:
 * - index 在合法范围内(0 ≤ index < length) -> 替换该位置
 * - 负数 index -> 前置插入
 * - 超出范围的正数 index -> 追加到末尾
 */
export function upsertPortPair(
  pairs: ReadonlyArray<NetworkPortPair>,
  index: number,
  next: NetworkPortPair,
): NetworkPortPair[] {
  const result = pairs.slice();
  if (index < 0) {
    result.unshift(next);
    return result;
  }
  if (index >= result.length) {
    result.push(next);
    return result;
  }
  result[index] = next;
  return result;
}

/** 在指定 index 处删除一对端口;index 越界返回原列表的拷贝。 */
export function removePortPair(
  pairs: ReadonlyArray<NetworkPortPair>,
  index: number,
): NetworkPortPair[] {
  if (index < 0 || index >= pairs.length) return pairs.slice();
  const result = pairs.slice();
  result.splice(index, 1);
  return result;
}

/**
 * 若列表为空,确保至少有一对(空对象形态);否则原样返回。
 * 用于"添加连线"对话框在用户未配对任何端口时给出可视占位,
 * 校验阶段仍要求 ≥ 1 对合法端口才允许保存。
 */
export function ensureMinimumPortPair(
  pairs: ReadonlyArray<NetworkPortPair>,
): NetworkPortPair[] {
  if (pairs.length > 0) return pairs.slice();
  return [
    {
      source_interface: { bk_obj_id: 'bk_interface', bk_inst_id: 0, interface_name: '' },
      target_interface: { bk_obj_id: 'bk_interface', bk_inst_id: 0, interface_name: '' },
    },
  ];
}
